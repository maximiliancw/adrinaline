"""Read-only wrappers around the git executable. Never stage, commit or fetch."""

import os
import subprocess
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
    listing = run(["ls-tree", "--name-only", rev, "--", f"{rel}/"], root) if rel else None
    names = [n for n in (listing or "").splitlines() if n]
    if not names:
        raise AdrError("no-adr-dir", f"no ADR directory {rel} at {rev}", rev=rev)
    proc = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=root,
        input="".join(f"{rev}:{name}\n" for name in names).encode(),
        capture_output=True,
        check=True,
        env=_ENV,
    )
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


def log(root: Path | None, path: Path) -> list[dict[str, str]]:
    if root is None:
        raise AdrError("no-git", "adr log needs a git repository")
    out = run(["log", "--follow", "--format=%H%x1f%as%x1f%an%x1f%s", "--", str(path)], root) or ""
    keys = ("commit", "date", "author", "subject")
    return [dict(zip(keys, line.split("\x1f"), strict=True)) for line in out.splitlines() if line]


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
