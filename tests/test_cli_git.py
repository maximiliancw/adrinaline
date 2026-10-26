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
