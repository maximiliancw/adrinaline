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
