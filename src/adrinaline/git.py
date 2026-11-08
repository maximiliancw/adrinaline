"""Read-only wrappers around the git executable. Never stage, commit or fetch."""

import datetime as dt
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from adrinaline.model import FILENAME_RE, AdrError

_ENV = os.environ | {"GIT_OPTIONAL_LOCKS": "0"}


def run(args: list[str], cwd: Path, stdin: str | None = None) -> str | None:
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
    rel = _rel(root, directory)
    refs = run(["for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes"], root)
    if rel is None or refs is None:
        return {}
    found: dict[int, str] = {}
    for ref in refs.split():
        listing = run(["ls-tree", "--name-only", ref, "--", f"{rel}/"], root) or ""
        for line in listing.splitlines():
            if match := FILENAME_RE.match(PurePosixPath(line).name):
                found.setdefault(int(match[1]), ref)
    return found


def read_dir_at(root: Path | None, rev: str, directory: Path) -> list[tuple[Path, str]]:
    if root is None:
        raise AdrError("no-git", "--at needs a git repository")
    if run(["rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"], root) is None:
        raise AdrError("bad-revision", f"unknown git revision: {rev}", rev=rev)
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


def commits_since(root: Path, since: dt.date, rev: str | None = None) -> list[Commit]:
    """Non-merge commits reachable from rev (default HEAD) since a date, newest first, with
    the files each one touched. [] when git fails (for example no commits yet)."""
    # Records are separated by RS (\x1e), header fields by US (\x1f); file names follow the
    # header one per line. ponytail: core.quotePath=false keeps non-ASCII names readable; a
    # name containing a newline is still C-quoted by git and would be miscounted.
    fmt = "--format=%x1e%H%x1f%cs%x1f%s"
    # --since is compared in the committer's own timezone, so a commit made early the next day
    # in a far-east zone can look older than the baseline; start a day early and let
    # drift.compute do the exact committer-day comparison.
    start = since - dt.timedelta(days=1)
    args = [
        "log",
        "--no-merges",
        "--name-only",
        f"--since={start.isoformat()}",
        fmt,
        rev or "HEAD",
        "--",
    ]
    out = run(args, root) or ""
    commits: list[Commit] = []
    for record in out.split("\x1e"):
        header, _, rest = record.partition("\n")
        if not header:
            continue
        sha, date, subject = header.split("\x1f", 2)
        files = tuple(sorted(f for f in rest.split("\n") if f))
        commits.append(Commit(sha, dt.date.fromisoformat(date), subject, files))
    return commits


def changed_files(root: Path, base: str) -> list[str]:
    diff = run(["diff", "--name-only", base, "--"], root)
    if diff is None:
        raise AdrError("bad-revision", f"cannot diff against {base}", rev=base)
    untracked = run(["ls-files", "--others", "--exclude-standard"], root) or ""
    return sorted({*diff.splitlines(), *untracked.splitlines()} - {""})


def working_changes(root: Path) -> list[str]:
    # ponytail: porcelain v1 quotes odd filenames; switch to `-z` if such paths matter
    out = run(["status", "--porcelain", "--untracked-files=all"], root) or ""
    return sorted(
        {line[3:].split(" -> ")[-1].strip('"') for line in out.splitlines() if len(line) > 3}
    )


def tracked_files(root: Path) -> list[str]:
    out = run(["ls-files", "--cached", "--others", "--exclude-standard"], root) or ""
    return [line for line in out.splitlines() if line]


def files_at(root: Path, rev: str) -> list[str]:
    out = run(["ls-tree", "-r", "--name-only", rev], root) or ""
    return [line for line in out.splitlines() if line]
