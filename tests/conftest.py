"""Shared fixtures: a throwaway git repository and an `adr` runner."""

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ENV = {k: v for k, v in os.environ.items() if k != "ADR_DIR"} | {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "EDITOR": "true",
    "VISUAL": "true",
}


@dataclass
class Result:
    code: int
    out: str
    err: str

    def json(self):
        return json.loads(self.out)


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.adr_dir = root / "docs" / "adr"

    def adr(
        self,
        *args: str,
        cwd: Path | None = None,
        stdin: str | None = None,
        env: dict[str, str] | None = None,
    ) -> Result:
        proc = subprocess.run(
            [sys.executable, "-m", "adrinaline", *args],
            cwd=cwd or self.root,
            input=stdin,
            capture_output=True,
            text=True,
            env=ENV | (env or {}),
        )
        return Result(proc.returncode, proc.stdout, proc.stderr)

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.root, check=True, capture_output=True, text=True, env=ENV
        ).stdout

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_adr(
        self, number: int, slug: str, *, title: str | None = None, body: str = "", **meta: object
    ) -> Path:
        fields = {"status": "accepted", "date": "2026-01-15"} | {
            k.replace("_", "-"): v for k, v in meta.items()
        }
        front = "".join(f"{k}: {json.dumps(v)}\n" for k, v in fields.items())
        heading = title or slug.replace("-", " ").capitalize()
        return self.write(
            f"docs/adr/{number:04d}-{slug}.md", f"---\n{front}---\n# {heading}\n\n{body}"
        )

    def path_of(self, number: int) -> Path:
        return next(self.adr_dir.glob(f"{number:04d}-*.md"))

    def commit_all(self, message: str = "snapshot") -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    root = (tmp_path / "repo").resolve()
    root.mkdir()
    w = Workspace(root)
    w.git("init", "-q", "-b", "main")
    w.git("config", "user.name", "Test User")
    w.git("config", "user.email", "test@example.com")
    w.git("config", "commit.gpgsign", "false")
    return w


@pytest.fixture
def initialized(ws: Workspace) -> Workspace:
    result = ws.adr("init")
    assert result.code == 0, result.err
    return ws
