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
