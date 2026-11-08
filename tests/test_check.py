import re
from pathlib import Path

import pytest

from adrinaline.check import run_checks
from adrinaline.repo import parse_all

GOOD = "---\nstatus: accepted\ndate: 2026-01-15\n---\n# A\n"


def codes(findings):
    return {(f.code, f.severity) for f in findings}


def test_clean_set_has_no_findings():
    s = parse_all([(Path("d/0001-a.md"), GOOD), (Path("d/0002-b.md"), GOOD)])
    assert run_checks(s, template_exists=True) == []


def test_duplicates_gaps_and_template():
    s = parse_all(
        [
            (Path("d/0001-a.md"), GOOD),
            (Path("d/0004-x.md"), GOOD),
            (Path("d/0004-y.md"), GOOD),
        ]
    )
    found = codes(run_checks(s, template_exists=False))
    assert found == {
        ("duplicate-number", "error"),
        ("number-gap", "warning"),
        ("no-template", "warning"),
    }


def test_broken_file_number_is_not_a_gap():
    s = parse_all(
        [(Path("d/0001-a.md"), GOOD), (Path("d/0002-b.md"), "broken"), (Path("d/0003-c.md"), GOOD)]
    )
    assert codes(run_checks(s, template_exists=True)) == {("no-frontmatter", "error")}


def adr_text(status="accepted", **rel):
    lines = [f"status: {status}", "date: 2026-01-15"] + [
        f"{k.replace('_', '-')}: {v}" for k, v in rel.items()
    ]
    return "---\n" + "\n".join(lines) + "\n---\n# T\n"


@pytest.mark.parametrize(
    ("files", "code"),
    [
        ({1: adr_text(depends_on=[7])}, "dangling-relation"),
        ({1: adr_text(relates_to=[1])}, "self-relation"),
        ({1: adr_text(), 2: adr_text(supersedes=[1])}, "asymmetric-relation"),
        ({1: adr_text("superseded", superseded_by=[2]), 2: adr_text()}, "asymmetric-relation"),
        ({1: adr_text(depends_on=[2]), 2: adr_text(depends_on=[1])}, "cycle"),
        ({1: adr_text("superseded"), 2: adr_text()}, "status-mismatch"),
        ({1: adr_text(superseded_by=[2]), 2: adr_text(supersedes=[1])}, "status-mismatch"),
    ],
)
def test_relation_rules(files, code):
    s = parse_all([(Path(f"d/{n:04d}-x{n}.md"), text) for n, text in files.items()])
    assert code in {f.code for f in run_checks(s, template_exists=True)}


def test_consistent_supersession_is_clean():
    s = parse_all(
        [
            (Path("d/0001-a.md"), adr_text("superseded", superseded_by=[2])),
            (Path("d/0002-b.md"), adr_text(supersedes=[1])),
        ]
    )
    assert run_checks(s, template_exists=True) == []


def test_self_relation_is_not_also_a_cycle():
    s = parse_all([(Path("d/0001-a.md"), adr_text(depends_on=[1]))])
    found = {f.code for f in run_checks(s, template_exists=True)}
    assert "self-relation" in found and "cycle" not in found


def test_gap_taken_elsewhere_is_not_reported():
    s = parse_all([(Path("d/0001-a.md"), GOOD), (Path("d/0003-c.md"), GOOD)])
    assert codes(run_checks(s, template_exists=True)) == {("number-gap", "warning")}
    assert run_checks(s, template_exists=True, taken_elsewhere={2}) == []


def test_snake_case_relation_key_warns():
    text = "---\nstatus: accepted\ndate: 2026-01-15\ndepends_on: [1]\n---\n# A\n"
    s = parse_all([(Path("d/0001-a.md"), text)])
    found = run_checks(s, template_exists=True)
    assert [(f.code, f.severity) for f in found] == [("unknown-relation-key", "warning")]
    assert "depends-on" in found[0].message


# --- CLI: every §11 code through `adr check --json` (AC10) ---

SPEC = Path(__file__).parent.parent / "docs" / "SPEC.md"


def _governed_change(w):
    w.write("src/db/conn.py", "x\n")
    w.write_adr(2, "db", scope=["src/db/**"])
    w.commit_all()
    w.write("src/db/conn.py", "y\n")


def _stale(w):
    w.write(".adrinaline.toml", "drift-commits = 1\n")
    w.write_adr(2, "x", scope=["src/**"])
    w.write("src/a.py", "x\n")
    w.commit_all()


FRONT = "---\nstatus: accepted\ndate: 2026-01-15\n"
CLI_CASES = {
    "bad-filename": lambda w: w.write("docs/adr/notes.md", "# Notes\n"),
    "no-frontmatter": lambda w: w.write("docs/adr/0002-x.md", "broken\n"),
    "missing-field": lambda w: w.write("docs/adr/0002-x.md", "---\nstatus: accepted\n---\n# X\n"),
    "bad-field": lambda w: w.write_adr(2, "x", depends_on="one"),
    "bad-status": lambda w: w.write_adr(2, "x", status="bogus"),
    "bad-date": lambda w: w.write_adr(2, "x", date="yesterday"),
    "no-title": lambda w: w.write("docs/adr/0002-x.md", f"{FRONT}---\nno heading\n"),
    "duplicate-number": lambda w: (w.write_adr(2, "x"), w.write_adr(2, "y")),
    "dangling-relation": lambda w: w.write_adr(2, "x", depends_on=[7]),
    "asymmetric-relation": lambda w: w.write_adr(2, "x", supersedes=[1]),
    "self-relation": lambda w: w.write_adr(2, "x", relates_to=[2]),
    "cycle": lambda w: (w.write_adr(2, "x", depends_on=[3]), w.write_adr(3, "y", depends_on=[2])),
    "status-mismatch": lambda w: w.write_adr(2, "x", status="superseded"),
    "number-gap": lambda w: w.write_adr(3, "x"),
    "no-template": lambda w: (w.adr_dir / ".template.md").unlink(),
    "bad-scope": lambda w: w.write_adr(2, "x", scope=["/etc/**"]),
    "unknown-relation-key": lambda w: w.write(
        "docs/adr/0002-x.md", f"{FRONT}depends_on: [1]\n---\n# X\n"
    ),
    "scope-matches-nothing": lambda w: w.write_adr(2, "x", scope=["nowhere/**"]),
    "scoped-change": _governed_change,
    "review-overdue": lambda w: w.write_adr(2, "x", review_by="2000-01-01"),
    "stale-decision": _stale,
}


def spec_severities() -> dict[str, str]:
    section = SPEC.read_text().split("## 11.")[1].split("\n## ")[0]
    return dict(re.findall(r"^\| `([a-z-]+)` \| (error|warning) \|", section, re.M))


def test_cli_cases_cover_spec_section_11():
    assert set(spec_severities()) == set(CLI_CASES)


@pytest.mark.parametrize("code", CLI_CASES)
def test_every_check_code_is_reported_by_the_cli(initialized, code):  # AC10
    CLI_CASES[code](initialized)
    args = ("--diff", "HEAD") if code == "scoped-change" else ()
    result = initialized.adr("check", *args, "--json")
    severity = spec_severities()[code]
    assert result.code == (1 if severity == "error" else 0), result.err
    assert (code, severity) in {(f["code"], f["severity"]) for f in result.json()["findings"]}


def test_check_json_shape(initialized):  # AC10
    assert initialized.adr("check", "--json").json() == {"ok": True, "findings": []}
    initialized.write_adr(3, "x", depends_on=[7])  # one error, one warning
    data = initialized.adr("check", "--json").json()
    assert set(data) == {"ok", "findings"} and data["ok"] is False
    assert {f["severity"] for f in data["findings"]} == {"error", "warning"}
    for finding in data["findings"]:
        assert set(finding) == {"code", "severity", "path", "message"}
        assert all(isinstance(v, str) for v in finding.values())


def test_review_overdue_only_for_adrs_in_force(initialized):  # AC25
    w = initialized
    w.write_adr(2, "x", review_by="2000-01-01")
    w.write_adr(3, "p", status="proposed", review_by="2000-01-01")
    w.write_adr(4, "old", status="superseded", superseded_by=[5], review_by="2000-01-01")
    w.write_adr(5, "new", supersedes=[4])
    result = w.adr("check", "--json")
    assert result.code == 0
    overdue = [f["path"] for f in result.json()["findings"] if f["code"] == "review-overdue"]
    assert overdue == ["docs/adr/0002-x.md"]
    assert "adr review 2" in result.out
    assert w.adr("check", "--strict").code == 1


def test_stale_decision_respects_the_threshold(initialized):  # AC27
    w = initialized
    w.write_adr(2, "db", scope=["src/db/**"])
    w.commit_all("adrs")
    w.write("src/db/conn.py", "1\n")
    w.commit_all("db one")
    w.write("src/db/pool.py", "1\n")
    w.commit_all("db two")

    def stale():
        return [
            f for f in w.adr("check", "--json").json()["findings"] if f["code"] == "stale-decision"
        ]

    assert stale() == []  # default: off
    w.write(".adrinaline.toml", "drift-commits = 3\n")
    assert stale() == []
    w.write(".adrinaline.toml", "drift-commits = 2\n")
    found = stale()
    assert len(found) == 1 and "2 commits" in found[0]["message"]
    assert "adr review 2" in found[0]["message"]
    assert found[0]["path"] == "docs/adr/0002-db.md"
