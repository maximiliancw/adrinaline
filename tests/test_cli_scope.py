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
