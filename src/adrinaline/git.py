"""Read-only wrappers around the git executable. Never stage, commit or fetch."""

import subprocess
from pathlib import Path


def run(args: list[str], cwd: Path, stdin: str | None = None) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotePath=false", *args],
            cwd=cwd,
            input=stdin,
            capture_output=True,
            text=True,
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
