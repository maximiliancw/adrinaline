"""Read-only wrappers around the git executable. Never stage, commit or fetch."""

import datetime as dt
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from adrinaline.model import FILENAME_RE, AdrError

_ENV = os.environ | {"GIT_OPTIONAL_LOCKS": "0"}


def run(args: list[str], cwd: Path, stdin: str | None = None) -> str | None:
    """Run git and return stdout, or None if git exits non-zero or is not installed. The two
    cases look the same to the caller; it never raises."""
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotePath=false", *args],
            cwd=cwd,
            input=stdin,
            capture_output=True,
            text=True,
            env=_ENV,
        )
    except FileNotFoundError:
        return None
    return proc.stdout if proc.returncode == 0 else None


def toplevel(cwd: Path) -> Path | None:
    out = run(["rev-parse", "--show-toplevel"], cwd)
    return Path(out.strip()).resolve() if out else None


def user_name(cwd: Path) -> str | None:
    out = run(["config", "user.name"], cwd)
    return out.strip() or None if out else None


def _rel(root: Path, directory: Path) -> str | None:
    try:
        return directory.relative_to(root).as_posix()
    except ValueError:
        return None


def numbers_on_refs(root: Path, directory: Path) -> dict[int, str]:
    """ADR numbers in `directory` on local branches and remote-tracking refs, each mapped to the
    first ref (in refname order) that has it. The current branch is skipped. `{}` if `directory`
    is outside `root` or the refs cannot be listed."""
    rel = _rel(root, directory)
    refs = run(["for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes"], root)
    if rel is None or refs is None:
        return {}
    # Exclude the current branch - we only care about numbers on OTHER branches
    current = run(["rev-parse", "--abbrev-ref", "HEAD"], root)
    current_branch = current.strip() if current else None
    found: dict[int, str] = {}
    for ref in refs.split():
        if current_branch and ref == current_branch:
            continue
        listing = run(["ls-tree", "--name-only", ref, "--", f"{rel}/"], root) or ""
        for line in listing.splitlines():
            if match := FILENAME_RE.match(PurePosixPath(line).name):
                found.setdefault(int(match[1]), ref)
    return found


def verify_rev(root: Path, rev: str) -> None:
    """Fail with bad-revision unless rev names a commit; `--end-of-options` keeps a rev such as
    `--output=f` from reaching git as an option."""
    if (
        run(["rev-parse", "--verify", "--quiet", "--end-of-options", f"{rev}^{{commit}}"], root)
        is None
    ):
        raise AdrError("bad-revision", f"unknown git revision: {rev}", rev=rev)


def read_dir_at(root: Path | None, rev: str, directory: Path) -> list[tuple[Path, str]]:
    """`(path, text)` for each file directly in `directory` at `rev`, as `repo.parse_all` takes.

    Subdirectories and missing objects are skipped; undecodable bytes are replaced. Raises
    `no-git` (no repository or git), `bad-revision`, or `no-adr-dir` (outside the repository or
    absent at `rev`).
    """
    if root is None:
        raise AdrError("no-git", "--at needs a git repository")
    verify_rev(root, rev)
    rel = _rel(root, directory)
    if rel is None:
        raise AdrError(
            "no-adr-dir",
            f"ADR directory {directory} is outside the git repository; --at needs it inside",
            rev=rev,
        )
    listing = run(["ls-tree", "--name-only", rev, "--", f"{rel}/"], root)
    names = [n for n in (listing or "").splitlines() if n]
    if not names:
        raise AdrError("no-adr-dir", f"no ADR directory {rel} at {rev}", rev=rev)
    try:
        proc = subprocess.run(
            ["git", "cat-file", "--batch"],
            cwd=root,
            input="".join(f"{rev}:{name}\n" for name in names).encode(),
            capture_output=True,
            check=True,
            env=_ENV,
        )
    except FileNotFoundError as exc:
        raise AdrError("no-git", "git executable not found") from exc
    except subprocess.CalledProcessError as exc:
        raise AdrError("bad-revision", f"cannot read {rev}: git cat-file failed", rev=rev) from exc
    data, items, pos = proc.stdout, [], 0
    for name in names:
        end = data.index(b"\n", pos)
        header = data[pos:end].split()
        pos = end + 1
        if len(header) < 3:  # "<object> missing"
            continue
        size = int(header[2])
        if header[1] == b"blob":
            items.append((root / name, data[pos : pos + size].decode("utf-8", errors="replace")))
        pos += size + 1
    return items


def log(root: Path | None, path: Path, rev: str | None = None) -> list[dict[str, str]]:
    """Commits that touched `path`, following renames, newest first, from `rev` (default HEAD).

    Each row has `commit`, `date`, `author` and `subject`. Raises `no-git` without a repository;
    `[]` when git fails.
    """
    if root is None:
        raise AdrError("no-git", "adr log needs a git repository")
    fmt = "--format=%H%x1f%as%x1f%an%x1f%s"
    # NUL-separated: str.splitlines() would also split a subject on U+2028, U+0085, \f, \x1c-\x1e
    out = run(["log", "-z", "--follow", fmt, rev or "HEAD", "--", str(path)], root) or ""
    keys = ("commit", "date", "author", "subject")
    return [dict(zip(keys, rec.split("\x1f"), strict=True)) for rec in out.split("\0") if rec]


@dataclass(frozen=True)
class Commit:
    sha: str
    date: dt.date  # committer date
    subject: str
    files: tuple[str, ...]
    adrs: tuple[int, ...] = ()  # numbers cited by `ADR:` trailers (SPEC §13)
    exempt: str | None = None  # reason from `ADR-Exempt:`


# Records are separated by RS (\x1e), header fields by US (\x1f); file names follow the header
# one per line. The subject comes last so a stray US in it cannot shift the fields. ponytail:
# core.quotePath=false keeps non-ASCII names readable; a name containing a newline is still
# C-quoted by git and would be miscounted.
_LOG_FORMAT = (
    "--format=%x1e%H%x1f%cs"
    "%x1f%(trailers:key=ADR,valueonly,unfold,separator=%x2c)"
    "%x1f%(trailers:key=ADR-Exempt,valueonly,unfold,separator=%x20)"
    "%x1f%s"
)


def _numbers(raw: str) -> tuple[int, ...]:
    return tuple(int(t) for t in re.split(r"[\s,]+", raw) if t.isascii() and t.isdigit())


def _commit_log(root: Path, args: list[str], files: bool = True) -> list[Commit]:
    names = ["--name-only"] if files else []
    out = run(["log", "--no-merges", *names, _LOG_FORMAT, *args, "--"], root) or ""
    commits: list[Commit] = []
    for record in out.split("\x1e"):
        header, _, rest = record.partition("\n")
        if not header:
            continue
        sha, date, adrs, exempt, subject = header.split("\x1f", 4)
        paths = tuple(sorted(f for f in rest.split("\n") if f))
        day = dt.date.fromisoformat(date)
        commits.append(Commit(sha, day, subject, paths, _numbers(adrs), exempt.strip() or None))
    return commits


def commits_since(root: Path, since: dt.date, rev: str | None = None) -> list[Commit]:
    """Non-merge commits reachable from rev (default HEAD) since a date, newest first, with
    the files each one touched. [] when git fails (for example no commits yet)."""
    # --since is compared in the committer's own timezone, so a commit made early the next day
    # in a far-east zone can look older than the baseline; start a day early and let
    # drift.compute do the exact committer-day comparison.
    start = since - dt.timedelta(days=1)
    return _commit_log(root, [f"--since={start.isoformat()}", rev or "HEAD"])


def commits_in(root: Path, revs: str, files: bool = True) -> list[Commit]:
    """Non-merge commits of a revision or range (`HEAD`, `base..HEAD`), newest first, with
    trailers and (unless files=False) the files each one touched. [] when git fails."""
    return _commit_log(root, [revs], files)


def changed_files(root: Path, base: str) -> list[str]:
    verify_rev(root, base)
    diff = run(["diff", "--name-only", base, "--"], root)
    if diff is None:
        raise AdrError("bad-revision", f"cannot diff against {base}", rev=base)
    untracked = run(["ls-files", "--others", "--exclude-standard"], root) or ""
    return sorted({*diff.splitlines(), *untracked.splitlines()} - {""})


def working_changes(root: Path) -> list[str]:
    # Porcelain v1 with -z: NUL-terminated, no quoting. A rename or copy ("R" or
    # "C" in either status column, e.g. "RM") is "XY new\0old\0"; all others "XY name\0".
    out = run(["status", "--porcelain", "-z", "--untracked-files=all"], root) or ""
    paths: set[str] = set()
    entries = iter(out.split("\0"))
    for entry in entries:
        if not entry:
            continue
        paths.add(entry[3:])  # skip the two status bytes and the space
        if entry[0] in "RC" or entry[1] in "RC":
            next(entries, None)  # drop the old name
    return sorted(paths)


def tracked_files(root: Path) -> list[str]:
    out = run(["ls-files", "--cached", "--others", "--exclude-standard"], root) or ""
    return [line for line in out.splitlines() if line]


def files_at(root: Path, rev: str) -> list[str]:
    out = run(["ls-tree", "-r", "--name-only", rev], root) or ""
    return [line for line in out.splitlines() if line]
