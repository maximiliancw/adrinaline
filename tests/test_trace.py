"""Commit trailers: git parsing, `adr trace` and the trailer checks (SPEC §13, AC31-33)."""

from adrinaline import git


def test_commits_in_reads_trailers(ws):
    ws.write("a.txt", "1\n")
    ws.commit_all("base")
    ws.write("a.txt", "2\n")
    ws.commit_all("cite\n\nADR: 0007, 12\nadr: 3\nADR-Exempt: generated")
    ws.write("a.txt", "3\n")
    ws.commit_all("body only\n\nADR: 9 is mentioned here\n\nfinal words")
    ws.write("a.txt", "4\n")
    ws.commit_all("junk\n\nADR: #5, seven, ７, 8")
    junk, body, cite = git.commits_in(ws.root, "HEAD~3..HEAD")
    assert (cite.subject, cite.adrs, cite.exempt, cite.files) == (
        "cite",
        (7, 12, 3),
        "generated",
        ("a.txt",),
    )
    assert (body.adrs, body.exempt) == ((), None)
    assert junk.adrs == (8,)


def test_commits_in_without_commits(ws):
    assert git.commits_in(ws.root, "HEAD") == []


def test_trace_lists_only_citing_commits(initialized):  # AC31
    w = initialized
    w.write_adr(2, "db")
    w.write_adr(3, "cache")
    w.commit_all("base")
    for i, trailer in enumerate(["ADR: 2", "ADR: 0002, 0003", "ADR: 3", ""]):
        w.write("src/x.py", f"{i}\n")
        w.commit_all(f"change {i}\n\n{trailer}".strip())
    rows = w.adr("trace", "2", "--json").json()
    assert [r["subject"] for r in rows] == ["change 1", "change 0"]
    assert rows[0]["adrs"] == [2, 3] and len(rows[0]["commit"]) == 40
    at = w.adr("trace", "2", "--at", "HEAD~3", "--json").json()
    assert [r["subject"] for r in at] == ["change 0"]
    assert len(w.adr("trace", "3").out.splitlines()) == 2
    uncited = w.adr("trace", "1")
    assert (uncited.code, uncited.out) == (0, "")


def test_trace_needs_git(tmp_path):
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    from adrinaline.cli import main

    assert main(["trace", "1", "--json"], cwd=tmp_path, env={}) == 3


def _db_repo(w):
    w.write_adr(2, "db", scope=["src/db/**"])
    w.write_adr(3, "cache", scope=["src/cache/**"])
    w.write("src/db/x.py", "0\n")
    w.write("src/cache/y.py", "0\n")
    w.commit_all("base")
    w.git("tag", "base")


def _codes(w, *extra):
    result = w.adr("check", "--diff", "base", *extra, "--json")
    return result.code, {(f["code"], f["severity"]) for f in result.json()["findings"]}


def test_uncited_change_without_or_with_unrelated_trailer(initialized):  # AC32
    w = initialized
    _db_repo(w)
    w.write("src/db/x.py", "1\n")
    w.commit_all("touch db")
    w.write("src/db/x.py", "2\n")
    w.commit_all("touch db again\n\nADR: 3")
    result = w.adr("check", "--diff", "base", "--json")
    uncited = [f for f in result.json()["findings"] if f["code"] == "uncited-change"]
    assert len(uncited) == 2 and all(f["path"] == "src/db/x.py" for f in uncited)
    assert "0002" in uncited[0]["message"] and "ADR: 2" in uncited[0]["message"]
    assert ("scoped-change", "warning") in _codes(w)[1]


def test_citing_commit_clears_both_warnings(initialized):  # AC32
    w = initialized
    _db_repo(w)
    w.write("src/db/x.py", "1\n")
    w.commit_all("touch db\n\nADR: 2")
    assert _codes(w, "--strict") == (0, set())
    w.write("src/db/x.py", "2\n")  # uncommitted edit
    assert _codes(w) == (0, {("scoped-change", "warning")})


def test_exempt_change_is_a_note(initialized):  # AC33
    w = initialized
    _db_repo(w)
    w.write("src/db/x.py", "1\n")
    w.commit_all("regenerate\n\nADR-Exempt: generated code")
    result = w.adr("check", "--diff", "base", "--strict", "--json")
    assert result.code == 0 and result.json()["ok"] is True
    (note,) = result.json()["findings"]
    assert (note["code"], note["severity"]) == ("exempt-change", "note")
    assert "generated code" in note["message"]


def test_citation_clears_scoped_change_only_for_files_it_governs(initialized):
    w = initialized
    _db_repo(w)
    w.write("src/db/x.py", "1\n")
    w.write("src/cache/y.py", "1\n")
    w.commit_all("touch both\n\nADR: 2")
    result = w.adr("check", "--diff", "base", "--json")
    found = {(f["code"], f["path"]) for f in result.json()["findings"]}
    assert found == {("scoped-change", "src/cache/y.py")}  # cites 0002, so not uncited


def test_merge_only_change_keeps_scoped_change(initialized):
    w = initialized
    _db_repo(w)
    w.git("switch", "-q", "-c", "side")
    w.write("other.txt", "side\n")
    w.commit_all("side edit")
    w.git("switch", "-q", "main")
    w.git("merge", "-q", "--no-ff", "--no-commit", "side")
    w.write("src/db/x.py", "1\n")  # edit made in the merge commit itself
    w.git("add", "-A")
    w.git("commit", "-q", "-m", "merge side\n\nADR: 2")
    codes = _codes(w)[1]
    assert ("scoped-change", "warning") in codes
    assert ("uncited-change", "warning") not in codes


def test_diff_rejects_option_like_ref(initialized):
    result = initialized.adr("check", "--diff=--output=leak.txt", "--json")
    assert result.code == 3 and result.json()["error"]["code"] == "bad-revision"
    assert not (initialized.root / "leak.txt").exists()
    initialized.commit_all("base")
    ranged = initialized.adr("check", "--diff", "HEAD..HEAD", "--json")
    assert ranged.code == 3 and ranged.json()["error"]["code"] == "bad-revision"
