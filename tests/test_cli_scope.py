import pytest


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


def test_numbers_taken_on_other_branches_are_not_gaps(initialized):
    initialized.write_adr(2, "second")
    initialized.commit_all()
    initialized.git("switch", "-q", "-c", "other")
    initialized.write_adr(3, "elsewhere")
    initialized.commit_all()
    initialized.git("switch", "-q", "main")
    assert initialized.adr("new", "Four").code == 0
    assert initialized.path_of(4)
    assert initialized.adr("check", "--strict").code == 0


def test_check_diff_outside_git(tmp_path):
    from conftest import Workspace

    w = Workspace(tmp_path.resolve())
    w.adr("init")
    result = w.adr("check", "--diff", "HEAD", "--json")
    assert result.code == 3 and result.json()["error"]["code"] == "no-git"


def test_check_diff_reports_untracked_new_file(initialized):
    scoped_repo(initialized)
    initialized.commit_all()
    initialized.write("src/db/new.py", "z\n")
    result = initialized.adr("check", "--diff", "HEAD", "--json")
    paths = {f["path"] for f in result.json()["findings"] if f["code"] == "scoped-change"}
    assert "src/db/new.py" in paths


def test_check_diff_ignores_changes_made_on_ref_after_the_branch_point(initialized):
    scoped_repo(initialized)
    initialized.commit_all()
    initialized.git("switch", "-q", "-c", "feature")
    initialized.git("switch", "-q", "main")
    initialized.write("src/db/conn.py", "main moved\n")
    initialized.commit_all()
    initialized.git("switch", "-q", "feature")
    assert initialized.adr("check", "--diff", "main", "--strict").code == 0


def test_check_diff_rejects_unrelated_history(initialized):
    scoped_repo(initialized)
    initialized.commit_all()
    lonely = initialized.git("commit-tree", "HEAD^{tree}", "-m", "unrelated").strip()
    result = initialized.adr("check", "--diff", lonely, "--json")
    assert result.code == 3 and result.json()["error"]["code"] == "bad-revision"


def test_scope_flow_new_accept_for(initialized):  # AC19
    initialized.write("src/db/conn.py", "x\n")
    assert initialized.adr("new", "Pool", "--scope", "src/db/**").code == 0
    assert initialized.adr("for", "src/db/conn.py", "--json").json()["src/db/conn.py"] == []
    assert initialized.adr("accept", "2").code == 0
    data = initialized.adr("for", "src/db/conn.py", "--json").json()
    assert [a["number"] for a in data["src/db/conn.py"]] == [2]


@pytest.mark.parametrize("glob", ["/abs/**", "../x/**"])
def test_bad_scope_exits_3_and_writes_nothing(initialized, glob):  # AC19
    result = initialized.adr("new", "Bad", "--scope", glob, "--json")
    assert result.code == 3, result.err
    assert result.json()["error"]["code"] == "bad-scope"
    assert not list(initialized.adr_dir.glob("0002-*"))
