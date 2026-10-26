# WP3 Git and scope: cross-branch numbers, log, `--at`, `adr for`, `check --diff` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect ADRs to git history and code: number allocation that sees other branches, `adr log`, read commands at any revision (`--at REF`), `scope` globs with `adr for PATH` and `adr check --diff REF`, and a guard proving the tool never writes to git.

**Architecture:** All git access stays in `git.py` (read-only subprocess calls, optional locks disabled). `repo.load` reads either the working tree or a revision. `AdrGraph.governing` answers "which ADRs in force cover this path". `check` gains scope rules. The CLI gets a `reads` parent parser that carries `--at` for read commands only.

**Tech Stack:** Python 3.14 (`PurePosixPath.full_match`), git CLI, existing modules.

**Spec:** `docs/SPEC.md` (§8 Revisions and "Governing ADRs of a path", §9 rows new/check/for/log, §10, §11 scope codes, §13, §16 criteria 5, 12, 15, 19, 20, 21). Requires WP1 and WP2.

## Global Constraints

- Git is read-only: allowed subcommands are `rev-parse`, `config` (read), `for-each-ref`, `ls-tree`, `cat-file`, `log`, `diff`, `ls-files`, `status`. Every call runs with `GIT_OPTIONAL_LOCKS=0` so not even the index stat cache is refreshed.
- No network: never `fetch`; remote refs are as fresh as the last fetch.
- Outside a git repository, git features degrade silently, except `adr log`, `--at` and `check --diff`, which fail with `no-git`.
- `--at` exists only on read commands (`show`, `list`, `index`, `graph`, `check`, `for`, and `prime` in WP4); mutating commands reject it with exit 2.
- Scope globs are repository-relative POSIX paths matched with `PurePosixPath.full_match`.
- With `--json`, stdout carries exactly one JSON document. Exit codes 0/1/2/3.
- English everywhere; no AI attribution; Conventional Commits. Lint, format, type check and tests pass after every task.

## Review Focus

1. Running `adr for` with a path relative to a subdirectory (`cd src/db && adr for conn.py`) must resolve to the repository-relative path → test in Task 3.
2. `--at` with an unknown revision, or a revision where the ADR directory did not exist yet, must give `bad-revision` / `no-adr-dir`, not a traceback → test in Task 2.
3. A repository with no commits yet (fresh `git init`) must still allow `adr new` and `adr log` (empty result) → test in Task 1.
4. An ADR directory outside the git root (`ADR_DIR=/elsewhere`) must not crash cross-branch allocation → test in Task 1.
5. Changed files that were deleted in the working tree must still be reported by `check --diff` if they were governed → test in Task 3.

---

### Task 1: Git reads, cross-branch numbering and `adr log`

**Files:**
- Modify: `src/adrinaline/git.py`
- Modify: `src/adrinaline/repo.py` (`next_number`)
- Modify: `src/adrinaline/cli.py` (add `cmd_log`, register it)
- Test: `tests/test_cli_git.py`

**Interfaces:**
- Produces: `git.numbers_on_refs(root: Path, directory: Path) -> dict[int, str]`; `git.read_dir_at(root: Path | None, rev: str, directory: Path) -> list[tuple[Path, str]]`; `git.log(root: Path | None, path: Path) -> list[dict[str, str]]` (keys `commit`, `date`, `author`, `subject`); `git.changed_files(root: Path, base: str) -> list[str]`; `git.working_changes(root: Path) -> list[str]`; `git.tracked_files(root: Path) -> list[str]`; `repo.next_number(loc)` now returns skipped numbers taken on other refs; CLI `adr log REF`.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli_git.py`:

```python
def test_new_skips_numbers_taken_on_other_branches(initialized):  # AC5
    initialized.adr("new", "Main two")
    initialized.commit_all()
    initialized.git("switch", "-q", "-c", "other")
    initialized.adr("new", "Other three")
    initialized.commit_all()
    initialized.git("switch", "-q", "main")
    result = initialized.adr("new", "Main next", "--json")
    assert result.code == 0, result.err
    assert result.json()["number"] == 4
    assert result.json()["skipped"] == {"0003": "other"}
    assert "skipped 0003, taken on other" in result.err


def test_new_works_before_first_commit(initialized):
    assert initialized.adr("new", "Early").code == 0
    assert initialized.adr("log", "2", "--json").json() == []


def test_adr_dir_outside_repository(ws, tmp_path):
    outside = tmp_path / "elsewhere"
    env = {"ADR_DIR": str(outside)}
    assert ws.adr("init", env=env).code == 0
    result = ws.adr("new", "Outside", "--json", env=env)
    assert result.code == 0, result.err
    assert result.json()["number"] == 2


def test_log_lists_commits(initialized):
    initialized.adr("new", "Use PostgreSQL")
    initialized.commit_all("add 0002")
    initialized.adr("accept", "2")
    initialized.commit_all("accept 0002")
    rows = initialized.adr("log", "2", "--json").json()
    assert [r["subject"] for r in rows] == ["accept 0002", "add 0002"]
    assert rows[0]["author"] == "Test User"
    assert "accept 0002" in initialized.adr("log", "2").out


def test_log_outside_git(tmp_path):
    from conftest import Workspace

    w = Workspace(tmp_path.resolve())
    w.adr("init")
    result = w.adr("log", "1", "--json")
    assert result.code == 3 and result.json()["error"]["code"] == "no-git"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_git.py -q`
Expected: FAIL (`skipped` is `{}`; `log` is an invalid choice).

- [ ] **Step 3: Extend `git.py`**

Replace `run` and add the new functions:

```python
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
            items.append((root / name, data[pos : pos + size].decode("utf-8")))
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
    return sorted({line[3:].split(" -> ")[-1].strip('"') for line in out.splitlines() if len(line) > 3})


def tracked_files(root: Path) -> list[str]:
    out = run(["ls-files", "--cached", "--others", "--exclude-standard"], root) or ""
    return [line for line in out.splitlines() if line]
```

Keep `toplevel` and `user_name` unchanged. `model` imports nothing from `git`, so there is no import cycle.

- [ ] **Step 4: Update `repo.next_number`**

```python
def next_number(loc: Location) -> tuple[int, dict[int, str]]:
    local = numbers_in(loc.dir)
    top = max(local, default=0)
    remote = git.numbers_on_refs(loc.root, loc.dir) if loc.root else {}
    skipped = {n: ref for n, ref in remote.items() if n > top}
    return max([top, *skipped]) + 1, skipped
```

- [ ] **Step 5: Add `cmd_log` to `cli.py`**

```python
def cmd_log(ctx: Ctx) -> None:
    adr = repo.resolve(ctx.load().adrs, ctx.args.ref)
    rows = git.log(ctx.loc.root, adr.path)
    text = "\n".join(f"{r['date']}  {r['commit'][:8]}  {r['author']}  {r['subject']}" for r in rows)
    ctx.out.result(rows, text or "no commits yet")
```

Register before `return parser`:

```python
    p = add("log", cmd_log, "show the git history of an ADR")
    p.add_argument("ref")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run ty check`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/adrinaline tests/test_cli_git.py
git commit -m "feat: cross-branch number allocation and adr log"
```

---

### Task 2: `--at REF` for read commands

**Files:**
- Modify: `src/adrinaline/repo.py` (`load`)
- Modify: `src/adrinaline/cli.py` (`Ctx.load`, `build_parser`)
- Test: `tests/test_cli_git.py` (append)

**Interfaces:**
- Produces: `repo.load(loc, at: str | None = None) -> AdrSet`; `build_parser` gains a `reads` parent parser with `--at REF` and `add(name, func, help_, *, reads: bool = False)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_git.py`:

```python
def test_at_reads_an_earlier_revision(initialized):  # AC21
    initialized.adr("new", "Use MySQL", "--accepted")
    initialized.adr("new", "Use PostgreSQL", "--accepted")
    initialized.commit_all("first")
    initialized.adr("supersede", "2", "--by", "3")
    initialized.commit_all("second")
    before = {a["number"]: a["status"] for a in initialized.adr("list", "--at", "HEAD~1", "--json").json()}
    now = {a["number"]: a["status"] for a in initialized.adr("list", "--json").json()}
    assert before[2] == "accepted" and now[2] == "superseded"
    assert initialized.adr("show", "2", "--at", "HEAD~1", "--json").json()["status"] == "accepted"
    assert initialized.adr("accept", "3", "--at", "HEAD~1").code == 2


def test_at_errors(initialized):
    initialized.commit_all("first")
    result = initialized.adr("list", "--at", "no-such-ref", "--json")
    assert result.code == 3 and result.json()["error"]["code"] == "bad-revision"
    initialized.write("README.md", "x\n")
    initialized.git("rm", "-q", "-r", "docs")
    initialized.commit_all("drop adrs")
    initialized.git("checkout", "-q", "HEAD~1", "--", "docs")
    result = initialized.adr("list", "--at", "HEAD", "--json")
    assert result.code == 3 and result.json()["error"]["code"] == "no-adr-dir"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_git.py -q -k at_`
Expected: FAIL (exit 2: unrecognized arguments `--at`).

- [ ] **Step 3: Implement**

In `repo.py`, replace `load`:

```python
def load(loc: Location, at: str | None = None) -> AdrSet:
    if at is not None:
        return parse_all(git.read_dir_at(loc.root, at, loc.dir))
    if not loc.dir.is_dir():
        raise no_dir(loc)
    paths = sorted(p for p in loc.dir.iterdir() if p.is_file())
    return parse_all((p, p.read_text(encoding="utf-8")) for p in paths)
```

In `cli.py`, change `Ctx.load`:

```python
    def load(self) -> repo.AdrSet:
        return repo.load(self.loc, getattr(self.args, "at", None))
```

In `build_parser`, add after `common`:

```python
    reads = argparse.ArgumentParser(add_help=False)
    reads.add_argument("--at", metavar="REF", help="read ADRs as of a git revision")
```

change `add`:

```python
    def add(
        name: str, func: Callable[[Ctx], int | None], help_: str, *, reads_: bool = False
    ) -> argparse.ArgumentParser:
        parents = [common, reads] if reads_ else [common]
        p = sub.add_parser(name, parents=parents, help=help_, description=help_)
        p.set_defaults(func=func)
        return p
```

and pass `reads_=True` when registering `show`, `list`, `index`, `check` and `graph`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run ty check`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/adrinaline tests/test_cli_git.py
git commit -m "feat: read ADRs at any git revision with --at"
```

---

### Task 3: Scope: `adr for` and `adr check --diff`

**Files:**
- Modify: `src/adrinaline/graph.py` (add `governing`)
- Modify: `src/adrinaline/check.py` (scope rules, new keyword parameters)
- Modify: `src/adrinaline/cli.py` (add `cmd_for`, extend `cmd_check`, register)
- Test: `tests/test_cli_scope.py`

**Interfaces:**
- Produces: `AdrGraph.governing(path: str, *, include_proposed: bool = False) -> list[Adr]`; `check.run_checks(s, *, template_exists, tracked: list[str] | None = None, changed: list[str] | None = None)` adding `scope-matches-nothing` and `scoped-change` (path = repository-relative changed file); CLI `adr for PATH... [--all]`, `adr check --diff REF`.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli_scope.py`:

```python
def scoped_repo(w):
    w.write("src/db/conn.py", "x\n")
    w.write("src/api/app.py", "x\n")
    w.write_adr(2, "old-db", status="superseded", scope=["src/db/**"], superseded_by=[3])
    w.write_adr(3, "new-db", scope=["src/db/**"], supersedes=[2])
    w.write_adr(4, "api-draft", status="proposed", scope=["src/api/**"])


def test_for_lists_adrs_in_force(initialized):  # AC19
    scoped_repo(initialized)
    result = initialized.adr("for", "src/db/conn.py", "src/api/app.py", "--json")
    assert result.code == 0, result.err
    data = result.json()
    assert [a["number"] for a in data["src/db/conn.py"]] == [3]
    assert data["src/api/app.py"] == []
    with_drafts = initialized.adr("for", "src/api/app.py", "--all", "--json").json()
    assert [a["number"] for a in with_drafts["src/api/app.py"]] == [4]


def test_for_resolves_paths_from_subdirectory(initialized):
    scoped_repo(initialized)
    sub = initialized.root / "src" / "db"
    data = initialized.adr("for", "conn.py", "--json", cwd=sub).json()
    assert [a["number"] for a in data["src/db/conn.py"]] == [3]


def test_check_diff_reports_scoped_changes(initialized):  # AC20
    scoped_repo(initialized)
    initialized.commit_all()
    assert initialized.adr("check", "--diff", "HEAD", "--strict").code == 0
    initialized.write("src/db/conn.py", "y\n")
    result = initialized.adr("check", "--diff", "HEAD", "--json")
    assert result.code == 0
    scoped = [f for f in result.json()["findings"] if f["code"] == "scoped-change"]
    assert len(scoped) == 1 and scoped[0]["path"] == "src/db/conn.py"
    assert "0003" in scoped[0]["message"]
    assert initialized.adr("check", "--diff", "HEAD", "--strict").code == 1


def test_check_diff_reports_deleted_files(initialized):
    scoped_repo(initialized)
    initialized.commit_all()
    (initialized.root / "src" / "db" / "conn.py").unlink()
    result = initialized.adr("check", "--diff", "HEAD", "--json")
    assert "src/db/conn.py" in {f["path"] for f in result.json()["findings"]}


def test_scope_that_matches_nothing(initialized):
    initialized.write_adr(2, "ghost", scope=["nowhere/**"])
    result = initialized.adr("check", "--json")
    assert result.code == 0
    assert "scope-matches-nothing" in {f["code"] for f in result.json()["findings"]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_scope.py -q`
Expected: FAIL (exit 2: invalid choice `for`, unrecognized `--diff`).

- [ ] **Step 3: Add `governing` to `AdrGraph`**

Add `from pathlib import PurePosixPath` to `graph.py` and the method:

```python
    def governing(self, path: str, *, include_proposed: bool = False) -> list[Adr]:
        candidates = self.in_force()
        if include_proposed:
            candidates += [a for _, a in sorted(self.nodes.items()) if a.status is Status.PROPOSED]
        target = PurePosixPath(path)
        return [adr for adr in candidates if any(target.full_match(g) for g in adr.scope)]
```

- [ ] **Step 4: Add scope rules to `check.py`**

Add `from pathlib import PurePosixPath`, then:

```python
def _scopes(
    s: AdrSet, graph: AdrGraph, tracked: list[str] | None, changed: list[str] | None
) -> list[Finding]:
    found: list[Finding] = []
    if tracked is not None:
        paths = [PurePosixPath(f) for f in tracked]
        for adr in s.adrs:
            for glob in adr.scope:
                if not any(p.full_match(glob) for p in paths):
                    found.append(
                        Finding("scope-matches-nothing", "warning", str(adr.path), f"{adr.id}: scope {glob!r} matches no file")
                    )
    for path in changed or []:
        if hits := graph.governing(path):
            names = ", ".join(f"{a.id} {a.title}" for a in hits)
            found.append(
                Finding("scoped-change", "warning", path, f"{path} is governed by {names}; review before merging")
            )
    return found
```

and change `run_checks`:

```python
def run_checks(
    s: AdrSet,
    *,
    template_exists: bool,
    tracked: list[str] | None = None,
    changed: list[str] | None = None,
) -> list[Finding]:
    graph = AdrGraph(s.adrs)
    findings = [
        *s.problems,
        *_duplicates(s),
        *_gaps(s),
        *_relations(s, graph),
        *_scopes(s, graph, tracked, changed),
    ]
    if not template_exists:
        findings.append(
            Finding("no-template", "warning", "", "template is missing; `adr init` recreates it")
        )
    return sorted(findings, key=lambda f: (f.path, f.code))
```

- [ ] **Step 5: Update `cli.py`**

Replace `cmd_check` and add `cmd_for`:

```python
def cmd_check(ctx: Ctx) -> int:
    root = ctx.loc.root
    if ctx.args.diff and root is None:
        raise AdrError("no-git", "--diff needs a git repository")
    findings = run_checks(
        ctx.load(),
        template_exists=ctx.loc.template.is_file(),
        tracked=git.tracked_files(root) if root else None,
        changed=git.changed_files(root, ctx.args.diff) if root and ctx.args.diff else None,
    )
    failed = any(f.severity == "error" for f in findings) or (ctx.args.strict and bool(findings))
    rows = [
        asdict(f) | {"path": ctx.out.rel(Path(f.path)) if Path(f.path).is_absolute() else f.path}
        for f in findings
    ]
    text = "\n".join(f"{r['severity']}: {r['code']}: {r['message']}" for r in rows) or "ok"
    ctx.out.result({"ok": not failed, "findings": rows}, text)
    return EXIT_FINDINGS if failed else EXIT_OK


def _repo_path(raw: str, cwd: Path, base: Path) -> str:
    try:
        return (cwd / raw).resolve().relative_to(base).as_posix()
    except ValueError:
        return Path(raw).as_posix()


def cmd_for(ctx: Ctx) -> None:
    graph = AdrGraph(ctx.load().adrs)
    base = ctx.loc.root or ctx.cwd
    data: dict[str, list[dict]] = {}
    lines: list[str] = []
    for raw in ctx.args.paths:
        path = _repo_path(raw, ctx.cwd, base)
        hits = graph.governing(path, include_proposed=ctx.args.all)
        data[path] = [adr_dict(a, ctx.out) for a in hits]
        lines.append(f"{path}:" if hits else f"{path}: no governing ADRs")
        lines += [f"  {a.id} {a.title} [{a.status}]" for a in hits]
    ctx.out.result(data, "\n".join(lines))
```

Add `--diff` to the `check` parser and register `for` before `return parser`:

```python
    p.add_argument("--diff", metavar="REF", help="also report changed files governed by ADRs")
```

```python
    p = add("for", cmd_for, "list the ADRs in force that govern each path", reads_=True)
    p.add_argument("paths", nargs="+", metavar="PATH")
    p.add_argument("--all", action="store_true", help="include proposed ADRs")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run ty check`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/adrinaline tests/test_cli_scope.py
git commit -m "feat: scope globs with adr for and check --diff"
```

---

### Task 4: Guards: no git writes, one JSON document everywhere

**Files:**
- Test: `tests/test_guards.py`

**Interfaces:**
- Consumes: every command so far. WP4 appends `prime` to both lists.

- [ ] **Step 1: Write the tests**

`tests/test_guards.py`:

```python
import json

MUTATIONS = [
    ["new", "A", "--accepted"],
    ["new", "B"],
    ["accept", "3"],
    ["link", "3", "depends-on", "2"],
    ["new", "C", "--supersedes", "2"],
    ["unlink", "3", "depends-on", "2"],
    ["renumber", "4", "--to", "9"],
]
READS = [
    ["show", "2"],
    ["list"],
    ["index"],
    ["graph"],
    ["graph", "3", "--reverse"],
    ["check"],
    ["check", "--diff", "HEAD"],
    ["for", "src/x.py"],
    ["log", "1"],
    ["list", "--at", "HEAD"],
    ["skill"],
]


def test_no_git_writes(initialized):  # AC15
    initialized.commit_all("baseline")
    head = initialized.git("rev-parse", "HEAD")
    index = (initialized.root / ".git" / "index").read_bytes()
    for args in MUTATIONS + READS:
        result = initialized.adr(*args)
        assert result.code in (0, 1), (args, result.err)
    assert initialized.git("rev-parse", "HEAD") == head
    assert (initialized.root / ".git" / "index").read_bytes() == index
    status = initialized.git("status", "--porcelain", "--untracked-files=all").splitlines()
    assert status and all(line[3:].startswith("docs/adr/") for line in status)


def test_every_command_emits_one_json_document(initialized):  # AC12
    initialized.commit_all("baseline")
    for args in [["init"], *MUTATIONS, *READS, ["show", "404"], ["accept", "1"]]:
        result = initialized.adr(*args, "--json")
        assert result.code in (0, 1, 3), (args, result.err)
        json.loads(result.out)
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_guards.py -q`
Expected: 2 passed. If `test_no_git_writes` fails on the index bytes, a git call is missing `GIT_OPTIONAL_LOCKS=0`; fix `git.run` or the `cat-file` call, not the test.

- [ ] **Step 3: Run the full suite and commit**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run ty check`
Expected: all pass.

```bash
git add tests/test_guards.py
git commit -m "test: guard against git writes and non-JSON output"
```
