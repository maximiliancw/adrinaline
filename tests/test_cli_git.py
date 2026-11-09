import argparse
import re

import pytest

from adrinaline.cli import build_parser


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


def test_new_does_not_report_current_branch_deleted_files(initialized):  # AC for adr-fl77
    """Deleted ADR on current branch is not reported as 'taken on <branch>'."""
    initialized.adr("new", "First")
    initialized.commit_all()
    initialized.adr("new", "Second")
    initialized.commit_all()
    # Delete the most recent ADR from working tree (but it's still in git history)
    # Find the highest numbered ADR
    files = sorted(initialized.adr_dir.glob("000*-*.md"))
    second_file = files[-1]  # Get the highest numbered one
    second_file.unlink()
    # Creating a new ADR should reuse the deleted number, not skip it
    result = initialized.adr("new", "Third", "--json")
    deleted_num = int(second_file.stem.split("-")[0])
    assert result.code == 0, result.err
    assert result.json()["number"] == deleted_num
    # The deleted number should NOT be in skipped because it's on the current branch
    assert f"{deleted_num:04d}" not in result.json()["skipped"]


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


def test_log_at_revision(initialized):
    initialized.adr("new", "Use PostgreSQL")
    initialized.commit_all("add 0002")
    initialized.adr("accept", "2")
    initialized.commit_all("accept 0002")
    rows = initialized.adr("log", "2", "--at", "HEAD~1", "--json").json()
    assert [r["subject"] for r in rows] == ["add 0002"]


def test_at_error_lists_every_read_command(initialized):
    sub = next(a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    reads = {name for name, p in sub.choices.items() if p.get_default("reads")}
    result = initialized.adr("--at", "HEAD", "new", "X")
    assert result.code == 2
    listed = set(re.findall(r"\((.*)\)", result.err)[0].split(", "))
    assert listed == reads
    assert {"prime", "log"} <= listed
    assert initialized.adr("--at", "", "new", "X").code == 2


def test_log_survives_unicode_line_separators_in_subject(initialized):
    initialized.adr("new", "Use PostgreSQL")
    initialized.commit_all("fix\u2028thing\x0c!")
    rows = initialized.adr("log", "2", "--json").json()
    assert [r["subject"] for r in rows] == ["fix\u2028thing\x0c!"]


def test_log_outside_git(tmp_path):
    from conftest import Workspace

    w = Workspace(tmp_path.resolve())
    w.adr("init")
    result = w.adr("log", "1", "--json")
    assert result.code == 3 and result.json()["error"]["code"] == "no-git"


def test_at_reads_an_earlier_revision(initialized):  # AC21
    initialized.adr("new", "Use MySQL", "--accepted")
    initialized.adr("new", "Use PostgreSQL", "--accepted")
    initialized.commit_all("first")
    initialized.adr("supersede", "2", "--by", "3")
    initialized.commit_all("second")
    before = {
        a["number"]: a["status"] for a in initialized.adr("list", "--at", "HEAD~1", "--json").json()
    }
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


def test_at_tolerates_binary_files(initialized):
    (initialized.root / "docs/adr/diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\x00")
    initialized.commit_all("add diagram")
    result = initialized.adr("list", "--at", "HEAD", "--json")
    assert result.code == 0, result.err
    assert result.json()


def test_at_is_global_flag(initialized):
    initialized.commit_all("first")
    initialized.adr("new", "Later")
    before = initialized.adr("--at", "HEAD", "list", "--json")
    assert before.code == 0, before.err
    assert before.json() == initialized.adr("list", "--at", "HEAD", "--json").json()
    assert initialized.adr("--at", "HEAD", "accept", "1").code == 2


def test_at_with_adr_dir_outside_repo(ws, tmp_path):
    env = {"ADR_DIR": str(tmp_path / "elsewhere")}
    ws.adr("init", env=env)
    ws.write("README.md", "x\n")
    ws.commit_all("first")
    result = ws.adr("list", "--at", "HEAD", "--json", env=env)
    err = result.json()["error"]
    assert result.code == 3 and err["code"] == "no-adr-dir"
    assert "None" not in err["message"] and "outside" in err["message"]


def test_check_at_uses_files_at_rev(initialized):
    initialized.write_adr(2, "db", scope=["src/db/**"])
    initialized.commit_all("adrs")
    initialized.write("src/db/conn.py", "x\n")
    plain = initialized.adr("check", "--json").json()
    at = initialized.adr("check", "--at", "HEAD", "--json").json()
    codes = lambda r: [f["code"] for f in r["findings"]]  # noqa: E731
    assert "scope-matches-nothing" not in codes(plain)
    assert "scope-matches-nothing" in codes(at)


def test_read_dir_at_git_failures(monkeypatch, tmp_path):
    import subprocess

    from adrinaline import git
    from adrinaline.model import AdrError

    monkeypatch.setattr(
        git, "run", lambda args, root: "docs/adr/0001-a.md" if "ls-tree" in args else "x"
    )
    monkeypatch.setattr(git, "_rel", lambda root, d: "docs/adr")
    for exc, code in [
        (FileNotFoundError(), "no-git"),
        (subprocess.CalledProcessError(1, "git"), "bad-revision"),
    ]:

        def boom(*a, _e=exc, **k):
            raise _e

        monkeypatch.setattr(subprocess, "run", boom)
        with pytest.raises(AdrError) as ei:
            git.read_dir_at(tmp_path, "HEAD", tmp_path / "docs/adr")
        assert ei.value.code == code


def test_working_changes_skips_old_name_of_edited_rename(ws):
    from adrinaline import git

    ws.write("src/db/a.py", "a\n")
    ws.commit_all()
    ws.git("mv", "src/db/a.py", "src/db/b.py")
    ws.write("src/db/b.py", "b\n")  # status "RM new\0old\0"
    assert git.working_changes(ws.root) == ["src/db/b.py"]
