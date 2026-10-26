import json


def setup_chain(w):
    """0001 (init), 0002 accepted, 0003 proposed."""
    w.adr("new", "Use MySQL", "--accepted")
    w.adr("new", "Use PostgreSQL")


def test_supersede_writes_both_sides(initialized):  # AC8
    setup_chain(initialized)
    result = initialized.adr("supersede", "2", "--by", "3")
    assert result.code == 0, result.err
    old, new = initialized.path_of(2).read_text(), initialized.path_of(3).read_text()
    assert "supersedes: [2]" in new
    assert "superseded-by: [3]" in old and "status: superseded" in old
    shown = initialized.adr("show", "2", "--json").json()
    assert shown["relations"] == {"superseded-by": [3]} and shown["successor"] == 3


def test_supersede_requires_accepted_target(initialized):
    setup_chain(initialized)
    result = initialized.adr("supersede", "3", "--by", "2", "--json")
    assert result.code == 3 and result.json()["error"]["code"] == "invalid-transition"


def test_new_with_supersedes(initialized):
    initialized.adr("new", "Use MySQL", "--accepted")
    result = initialized.adr("new", "Use PostgreSQL", "--supersedes", "mysql", "--json")
    assert result.code == 0, result.err
    assert result.json()["relations"] == {"supersedes": [2]}
    assert "status: superseded" in initialized.path_of(2).read_text()


def test_new_rejects_bad_reference_before_writing(initialized):
    result = initialized.adr("new", "Orphan", "--depends-on", "99")
    assert result.code == 3
    assert not list(initialized.adr_dir.glob("0002-*.md"))


def test_link_cycle_is_refused(initialized):  # AC9
    setup_chain(initialized)
    assert initialized.adr("link", "3", "depends-on", "2").code == 0
    result = initialized.adr("link", "2", "depends-on", "3", "--json")
    assert result.code == 3 and result.json()["error"]["code"] == "cycle"


def test_link_changes_only_declaring_adr(initialized):  # AC16
    setup_chain(initialized)
    before = initialized.path_of(2).read_text()
    assert initialized.adr("link", "3", "amends", "2").code == 0
    assert initialized.path_of(2).read_text() == before
    assert "amends: [2]" in initialized.path_of(3).read_text()
    assert initialized.adr("show", "2", "--json").json()["relations"]["amended-by"] == [3]


def test_link_is_idempotent_and_symmetric(initialized):
    setup_chain(initialized)
    initialized.adr("link", "3", "relates-to", "2")
    before = (initialized.path_of(2).read_text(), initialized.path_of(3).read_text())
    assert initialized.adr("link", "2", "relates-to", "3").code == 0
    assert initialized.adr("link", "3", "relates-to", "2").code == 0
    assert (initialized.path_of(2).read_text(), initialized.path_of(3).read_text()) == before
    assert initialized.adr("show", "2", "--json").json()["relations"] == {"relates-to": [3]}
    assert initialized.adr("unlink", "2", "relates-to", "3").code == 0
    assert "relates-to" not in initialized.path_of(3).read_text()


def test_self_link_is_refused(initialized):
    result = initialized.adr("link", "1", "relates-to", "1", "--json")
    assert result.code == 3 and result.json()["error"]["code"] == "self-relation"


def test_graph_json_and_formats(initialized):  # AC17 (CLI side)
    setup_chain(initialized)
    initialized.adr("link", "3", "depends-on", "1")
    data = initialized.adr("graph", "--format", "json").json()
    assert [n["number"] for n in data["nodes"]] == [1, 2, 3]
    assert data["edges"] == [{"from": 3, "to": 1, "relation": "depends-on"}]
    assert initialized.adr("graph", "--format", "mermaid").out.startswith("flowchart LR\n")
    assert initialized.adr("graph", "--format", "dot").out.startswith("digraph adr {\n")
    assert initialized.adr("graph", "3").out.splitlines()[1].startswith("  depends-on -> 0001")


def test_graph_reverse_is_the_impact_set(initialized):  # AC18
    for title in ("Base", "Uses base", "Tweaks user", "Merely related", "Unrelated"):
        initialized.adr("new", title, "--accepted")
    initialized.adr("link", "3", "depends-on", "2")
    initialized.adr("link", "4", "amends", "3")
    initialized.adr("link", "5", "relates-to", "2")
    initialized.adr("link", "6", "depends-on", "1")
    data = initialized.adr("graph", "2", "--reverse", "--json").json()
    assert sorted(n["number"] for n in data["nodes"]) == [2, 3, 4]


def test_graph_json_is_one_document(initialized):
    json.loads(initialized.adr("graph", "1", "--json").out)


def test_renumber_fixes_duplicates(initialized):  # AC11
    initialized.write_adr(2, "two")
    initialized.write_adr(3, "three", body="See [b](0004-dup-b.md).\n")
    initialized.write_adr(4, "dup-a")
    initialized.write_adr(4, "dup-b")
    result = initialized.adr("check", "--json")
    assert result.code == 1 and "duplicate-number" in {f["code"] for f in result.json()["findings"]}
    assert initialized.adr("renumber", "dup-b", "--to", "5").code == 0
    assert (initialized.adr_dir / "0005-dup-b.md").is_file()
    assert not (initialized.adr_dir / "0004-dup-b.md").exists()
    assert "[b](0005-dup-b.md)" in initialized.path_of(3).read_text()
    assert initialized.adr("check").code == 0


def test_renumber_rewrites_relations(initialized):
    initialized.write_adr(2, "two")
    initialized.write_adr(3, "three", depends_on=[2])
    assert initialized.adr("renumber", "2", "--to", "7").code == 0
    assert "depends-on: [7]" in initialized.path_of(3).read_text()


def test_renumber_refuses_taken_number(initialized):
    initialized.write_adr(2, "two")
    result = initialized.adr("renumber", "2", "--to", "1", "--json")
    assert result.code == 3 and result.json()["error"]["code"] == "exists"
    assert (initialized.adr_dir / "0002-two.md").is_file()
