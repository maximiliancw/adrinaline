import datetime as dt
import json

import pytest

TODAY = dt.date.today().isoformat()


def test_init_creates_template_and_first_adr(ws):  # AC1
    result = ws.adr("init")
    assert result.code == 0, result.err
    assert (ws.adr_dir / ".template.md").is_file()
    text = (ws.adr_dir / "0001-record-architecture-decisions.md").read_text()
    assert "status: accepted" in text and f"date: {TODAY}" in text
    assert "decision-makers: [Test User]" in text
    assert ws.adr("check").code == 0


def test_init_is_idempotent(initialized):  # AC2
    before = {p: p.read_text() for p in initialized.adr_dir.iterdir()}
    result = initialized.adr("init")
    assert result.code == 0 and "already initialised" in result.out
    assert {p: p.read_text() for p in initialized.adr_dir.iterdir()} == before


def test_new_from_subdirectory(initialized):  # AC3
    sub = initialized.root / "src" / "deep"
    sub.mkdir(parents=True)
    result = initialized.adr("new", "Use PostgreSQL", cwd=sub)
    assert result.code == 0, result.err
    assert result.out.strip() == "docs/adr/0002-use-postgresql.md"
    text = (initialized.adr_dir / "0002-use-postgresql.md").read_text()
    assert "status: proposed" in text and f"date: {TODAY}" in text and "# Use PostgreSQL" in text


def test_new_with_body_from_stdin_and_tags(initialized):
    result = initialized.adr(
        "new",
        "Cache with Redis",
        "--tag",
        "cache",
        "--body-file",
        "-",
        "--json",
        stdin="## Context and Problem Statement\n\nSlow.\n",
    )
    data = result.json()
    assert data["number"] == 2 and data["tags"] == ["cache"] and data["skipped"] == {}
    text = initialized.path_of(2).read_text()
    assert "# Cache with Redis\n\n## Context and Problem Statement\n\nSlow.\n" in text
    assert "## Considered Options" not in text


def test_new_accepted(initialized):
    assert initialized.adr("new", "Use X", "--accepted", "--json").json()["status"] == "accepted"


def test_directory_discovery_precedence(ws):  # AC4
    ws.write("pyproject.toml", '[tool.adrinaline]\ndir = "from-pyproject"\n')
    ws.write(".adr-dir", "from-adr-dir\n")
    sub = ws.root / "pkg"
    sub.mkdir()

    def where(**env):
        result = ws.adr("init", "--json", cwd=sub, env=env)
        assert result.code == 0, result.err
        return result.json()["dir"]

    assert where(ADR_DIR=str(ws.root / "from-env")) == "from-env"
    assert where() == "from-pyproject"
    ws.write(".adrinaline.toml", 'dir = "from-toml"\n')
    assert where() == "from-toml"
    (ws.root / ".adrinaline.toml").unlink()
    (ws.root / "pyproject.toml").unlink()
    assert where() == "from-adr-dir"
    (ws.root / ".adr-dir").unlink()
    assert where() == "docs/adr"


def test_show_resolves_references(initialized):  # AC6
    initialized.adr("new", "Use PostgreSQL")
    paths = {
        initialized.adr("show", ref, "--json").json()["path"] for ref in ("2", "0002", " postgres ")
    }
    assert paths == {"docs/adr/0002-use-postgresql.md"}
    result = initialized.adr("show", "zzz", "--json")
    assert result.code == 3 and result.json()["error"]["code"] == "not-found"


def test_ambiguous_reference(initialized):
    initialized.adr("new", "Use PostgreSQL")
    initialized.adr("new", "Use PostGIS")
    result = initialized.adr("show", "use-post", "--json")
    assert result.code == 3
    error = result.json()["error"]
    assert error["code"] == "ambiguous" and len(error["details"]["candidates"]) == 2


def test_status_transitions(initialized):  # AC7
    initialized.adr("new", "Use PostgreSQL")
    assert initialized.adr("accept", "2").code == 0
    result = initialized.adr("accept", "2", "--json")
    assert result.code == 3 and result.json()["error"]["code"] == "invalid-transition"
    assert initialized.adr("deprecate", "2").code == 0
    assert initialized.adr("accept", "2", "--force").code == 0


def test_hand_edits_survive_rewrite(initialized):  # AC13
    initialized.adr("new", "Use PostgreSQL")
    path = initialized.path_of(2)
    path.write_text(
        path.read_text().replace(
            "status: proposed", "status: proposed  # pending review\nowner: team-a"
        )
    )
    assert initialized.adr("accept", "2").code == 0
    text = path.read_text()
    assert "status: accepted  # pending review" in text and "owner: team-a" in text


def test_list_filters_and_index(initialized):
    initialized.adr("new", "Use PostgreSQL", "--tag", "db")
    initialized.adr("new", "Pipes | in titles")
    assert [a["number"] for a in initialized.adr("list", "--json").json()] == [1, 2, 3]
    assert [
        a["number"] for a in initialized.adr("list", "--status", "proposed", "--json").json()
    ] == [2, 3]
    assert [a["number"] for a in initialized.adr("list", "--tag", "db", "--json").json()] == [2]
    index = initialized.adr("index").out
    assert "| [0002](0002-use-postgresql.md) | Use PostgreSQL | proposed |" in index
    assert "Pipes \\| in titles" in index


def test_show_raw_and_skill_are_verbatim(initialized):
    assert initialized.adr("show", "1", "--raw").out == initialized.path_of(1).read_text()
    skill = initialized.adr("skill").out
    assert skill.startswith("---\nname: adr\n") and not skill.endswith("\n\n")


def test_missing_directory_is_a_domain_error(ws):
    result = ws.adr("list", "--json")
    assert result.code == 3 and result.json()["error"]["code"] == "no-adr-dir"


def test_outside_git(tmp_path):
    from conftest import Workspace

    w = Workspace(tmp_path.resolve())
    assert w.adr("init").code == 0
    assert (tmp_path / "docs" / "adr" / "0001-record-architecture-decisions.md").is_file()


def test_check_reports_and_strict(initialized):
    (initialized.adr_dir / ".template.md").unlink()
    assert initialized.adr("check").code == 0
    assert initialized.adr("check", "--strict").code == 1
    initialized.write("docs/adr/0002-broken.md", "no frontmatter\n")
    result = initialized.adr("check", "--json")
    assert result.code == 1
    broken = next(f for f in result.json()["findings"] if f["code"] == "no-frontmatter")
    assert broken["severity"] == "error" and broken["path"] == "docs/adr/0002-broken.md"


def test_json_mode_prints_one_document(initialized):  # AC12 (core commands)
    for args in (["list"], ["show", "1"], ["index"], ["check"], ["show", "nope"], ["skill"]):
        json.loads(initialized.adr(*args, "--json").out)


def test_usage_error_exits_2(initialized):
    assert initialized.adr("frobnicate").code == 2


def test_binary_file_in_adr_dir_is_tolerated(initialized):
    (initialized.adr_dir / "diagram.png").write_bytes(b"\x89PNG\xff\xfe\x00")
    (initialized.adr_dir / "0009-bin.md").write_bytes(b"\xff\xfe\x00")
    listed = initialized.adr("list", "--json")
    assert listed.code == 0
    assert listed.json()
    checked = initialized.adr("check", "--json")
    codes = {f["code"] for f in checked.json()["findings"]}
    assert {"bad-filename", "no-frontmatter"} <= codes


def test_global_flags_before_and_after_subcommand(initialized):
    assert initialized.adr("--json", "list").json() == initialized.adr("list", "--json").json()
    elsewhere = initialized.root / "other"
    elsewhere.mkdir()
    for args in (
        ("--dir", "../docs/adr", "list", "--json"),
        ("list", "--json", "--dir", "../docs/adr"),
    ):
        assert initialized.adr(*args, cwd=elsewhere).json()[0]["number"] == 1


def test_reject_with_dir(initialized):
    initialized.adr("new", "Thing")
    result = initialized.adr("--dir", "docs/adr", "reject", "thing", "--json")
    assert result.code == 0
    assert result.json()["status"] == "rejected"


def test_bad_config_envelope(initialized):
    initialized.write(".adrinaline.toml", "dir = [")
    result = initialized.adr("list", "--json")
    assert result.code == 3
    assert result.json()["error"]["code"] == "bad-config"
    initialized.write(".adrinaline.toml", "dir = 5\n")
    assert initialized.adr("list", "--json").json()["error"]["code"] == "bad-config"


def test_missing_body_file_is_io_error(initialized):
    result = initialized.adr("new", "X", "--body-file", "missing.txt", "--json")
    assert result.code == 3
    assert result.json()["error"]["code"] == "io"


def test_missing_editor_is_io_error(initialized):
    result = initialized.adr("new", "X", "--edit", "--json", env={"VISUAL": "no-such-editor-xyz"})
    assert result.code == 3
    assert result.json()["error"]["code"] == "io"


def test_broken_template_is_bad_template(initialized):
    (initialized.adr_dir / ".template.md").write_text("no frontmatter", encoding="utf-8")
    result = initialized.adr("new", "X", "--json")
    assert result.code == 3
    assert result.json()["error"]["code"] == "bad-template"


def test_blank_ref_is_not_found(initialized):
    result = initialized.adr("show", " ", "--json")
    assert result.code == 3
    assert result.json()["error"]["code"] == "not-found"


def test_scalar_template_tags_become_list():
    import datetime as dt

    from adrinaline import repo
    from adrinaline.model import Status

    text = repo.render_new(
        "---\ntags: solo\n---\n# {title}\n", "T", Status.PROPOSED, dt.date(2026, 1, 1), None, ["x"]
    )
    assert "tags: [solo, x]" in text


@pytest.mark.parametrize("editor", ['"unbalanced', "  "])
def test_new_edit_bad_editor_is_io_error(initialized, editor):
    r = initialized.adr("new", "T", "--edit", env={"VISUAL": editor, "EDITOR": editor})
    assert r.code == 3
    assert "io" in r.err or "editor" in r.err
