import json
import re
from pathlib import Path

import pytest

from adrinaline import __version__
from adrinaline.check import _release, run_checks
from adrinaline.output import github_annotation, gitlab_report
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


def _uncited(w):
    w.write_adr(2, "db", scope=["src/db/**"])
    w.commit_all()
    w.git("tag", "base")
    w.write("src/db/conn.py", "x\n")
    w.commit_all("touch db")


def _exempt(w):
    _uncited(w)
    w.write("src/db/conn.py", "y\n")
    w.commit_all("regenerate\n\nADR-Exempt: generated")


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
    "uncited-change": _uncited,
    "exempt-change": _exempt,
    "review-overdue": lambda w: w.write_adr(2, "x", review_by="2000-01-01"),
    "stale-decision": _stale,
    "stale-skill": lambda w: w.write(
        ".claude/skills/adr/SKILL.md", "---\nname: adr\nmetadata:\n  version: 0.0.1\n---\n"
    ),
}


def test_stale_skill_only_for_an_older_installed_version(initialized):
    assert initialized.adr("skill", "--install", ".agents/skills/adr").code == 0
    assert initialized.adr("check", "--json").json()["findings"] == []
    release = _release(__version__)
    path = initialized.root / ".agents/skills/adr/SKILL.md"
    path.write_text(re.sub(r"version: .*", f'version: "{release}.dev1+gabc"', path.read_text()))
    assert initialized.adr("check", "--json").json()["findings"] == []  # same release
    path.write_text(re.sub(r"version: .*", 'version: "{version}"', path.read_text()))
    assert initialized.adr("check", "--json").json()["findings"] == []  # npx skills / plugin copy
    CLI_CASES["stale-skill"](initialized)
    [finding] = initialized.adr("check", "--json").json()["findings"]
    assert finding["path"] == ".claude/skills/adr/SKILL.md"
    assert "0.0.1" in finding["message"]
    assert "adr skill --install .claude/skills/adr" in finding["message"]


def spec_severities() -> dict[str, str]:
    section = SPEC.read_text().split("## 11.")[1].split("\n## ")[0]
    return dict(re.findall(r"^\| `([a-z-]+)` \| (error|warning|note) \|", section, re.M))


def test_cli_cases_cover_spec_section_11():
    assert set(spec_severities()) == set(CLI_CASES)


@pytest.mark.parametrize("code", CLI_CASES)
def test_every_check_code_is_reported_by_the_cli(initialized, code):  # AC10
    CLI_CASES[code](initialized)
    args = {
        "scoped-change": ("--diff", "HEAD"),
        "uncited-change": ("--diff", "base"),
        "exempt-change": ("--diff", "base"),
    }.get(code, ())
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


# --- CI annotation formats ---

SNAPSHOTS = Path(__file__).parent / "snapshots"


@pytest.mark.parametrize("fmt", ["github", "gitlab"])
def test_check_ci_formats_match_snapshots(initialized, fmt):
    initialized.write_adr(3, "x", depends_on=[7])  # file error, set-wide warning
    result = initialized.adr("check", "--format", fmt)
    assert result.code == 1, result.err
    assert result.out == (SNAPSHOTS / f"check.{fmt}").read_text()


def test_check_ci_formats_report_notes(initialized):
    _exempt(initialized)
    gh = initialized.adr("check", "--diff", "base", "--format", "github").out
    assert "::notice file=src/db/conn.py,line=1,title=exempt-change::" in gh
    note = {"code": "c", "severity": "note", "path": "", "message": "m"}
    assert json.loads(gitlab_report([note], "docs/adr"))[0]["severity"] == "info"


def test_check_ci_formats_when_clean(initialized):
    assert initialized.adr("check", "--format", "github").out == ""
    assert initialized.adr("check", "--format", "gitlab").out == "[]\n"


def test_check_ci_formats_ignore_quiet(initialized):
    assert initialized.adr("-q", "check", "--format", "gitlab").out == "[]\n"


def test_gitlab_fingerprints_ignore_the_message_and_stay_unique():
    row = {"code": "c", "severity": "warning", "path": "p", "message": "abc123 touched p"}
    first = json.loads(gitlab_report([row, row | {"message": "x"}], "d"))
    again = json.loads(gitlab_report([row | {"message": "def456 touched p"}], "d"))
    assert first[0]["fingerprint"] == again[0]["fingerprint"] != first[1]["fingerprint"]


def test_check_format_with_json_is_a_usage_error(initialized):
    assert initialized.adr("check", "--format", "github", "--json").code == 2


def test_github_annotation_escapes_workflow_command_characters():
    row = {"code": "c", "severity": "warning", "path": "a,b:c.md", "message": "50%\nnext"}
    assert github_annotation(row) == "::warning file=a%2Cb%3Ac.md,line=1,title=c::50%25%0Anext"


FIXABLE = {
    "asymmetric-relation": CLI_CASES["asymmetric-relation"],
    "status-mismatch": lambda w: w.write_adr(2, "x", superseded_by=[1]),
    "unknown-relation-key": CLI_CASES["unknown-relation-key"],
    "no-template": CLI_CASES["no-template"],
}


@pytest.mark.parametrize("code", FIXABLE)
def test_fix_repairs_mechanical_findings(initialized, code):  # AC34
    FIXABLE[code](initialized)
    data = initialized.adr("check", "--fix", "--json").json()
    assert code in {f["code"] for f in data["fixed"]}
    assert data["findings"] == []
    again = initialized.adr("check", "--fix", "--json").json()
    assert again["fixed"] == [] and again["findings"] == []


def test_fix_renames_key_in_place(initialized):
    CLI_CASES["unknown-relation-key"](initialized)
    initialized.adr("check", "--fix")
    text = (initialized.adr_dir / "0002-x.md").read_text()
    assert text.startswith(f"{FRONT}depends-on: [1]\n---")


def test_fix_leaves_ambiguous_findings_alone(initialized):  # AC34
    CLI_CASES["status-mismatch"](initialized)  # superseded, successor unknown
    initialized.write("docs/adr/0003-y.md", f"{FRONT}depends_on: [1]\ndepends-on: [1]\n---\n# Y\n")
    before = {p: p.read_text() for p in initialized.adr_dir.glob("*.md")}
    result = initialized.adr("check", "--fix", "--json")
    assert result.code == 1
    data = result.json()
    assert data["fixed"] == []
    assert {"status-mismatch", "unknown-relation-key"} <= {f["code"] for f in data["findings"]}
    assert {p: p.read_text() for p in initialized.adr_dir.glob("*.md")} == before


def test_fix_output_and_usage(initialized):
    CLI_CASES["no-template"](initialized)
    result = initialized.adr("check", "--fix")
    assert result.code == 0
    assert result.out.startswith("fixed no-template")
    assert "fixed" not in initialized.adr("check", "--json").json()
    assert initialized.adr("check", "--fix", "--at", "HEAD").code == 2
    CLI_CASES["no-template"](initialized)
    gitlab = initialized.adr("check", "--fix", "--format", "gitlab")
    assert json.loads(gitlab.out) == []


def test_fix_repairs_what_a_renamed_key_reveals(initialized):
    initialized.write("docs/adr/0002-x.md", f"{FRONT}superseded_by: [3]\n---\n# X\n")
    initialized.write("docs/adr/0003-y.md", f"{FRONT}supersedes: [2]\n---\n# Y\n")
    data = initialized.adr("check", "--fix", "--json").json()
    assert data["findings"] == []


def test_fix_status_keeps_the_date(initialized):
    FIXABLE["status-mismatch"](initialized)
    initialized.adr("check", "--fix")
    text = initialized.path_of(2).read_text()
    assert re.search(r'^status: "?superseded"?$', text, re.M)
    assert re.search(r'^date: "?2026-01-15"?$', text, re.M)


def test_inverse_snake_keys_are_not_flagged():  # ADR 0003: inverses are derived, never stored
    front = "status: accepted\ndate: 2026-01-15\namended_by: [1]\ndependency_of: [1]\n"
    text = f"---\n{front}---\n# A\n"
    s = parse_all([(Path("d/0001-a.md"), text)])
    assert run_checks(s, template_exists=True) == []
