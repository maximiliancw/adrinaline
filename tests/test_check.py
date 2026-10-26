from pathlib import Path

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
