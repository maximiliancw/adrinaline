import datetime as dt
from pathlib import Path

import pytest

from adrinaline.model import AdrError, Status, parse_adr

P = Path("docs/adr/0002-use-postgresql.md")


def doc(front: str, body: str = "# Use PostgreSQL\n") -> str:
    return f"---\n{front}---\n{body}"


def test_parse_valid():
    adr = parse_adr(
        P,
        doc(
            "status: accepted\ndate: 2026-01-15\ntags: [db]\nsupersedes: [1]\n"
            "scope: ['src/db/**']\nowner: team-a\n"
        ),
    )
    assert (adr.number, adr.id, adr.slug, adr.title) == (
        2,
        "0002",
        "use-postgresql",
        "Use PostgreSQL",
    )
    assert adr.status is Status.ACCEPTED
    assert adr.date.isoformat() == "2026-01-15"
    assert adr.tags == ["db"] and adr.scope == ["src/db/**"]
    assert adr.relations["supersedes"] == [1] and adr.relations["amends"] == []
    assert adr.meta["owner"] == "team-a"


@pytest.mark.parametrize(
    ("front", "body", "code"),
    [
        ("date: 2026-01-15\n", "# T\n", "missing-field"),
        ("status: maybe\ndate: 2026-01-15\n", "# T\n", "bad-status"),
        ("status: accepted\ndate: soon\n", "# T\n", "bad-date"),
        ("status: accepted\ndate: 2026-01-15\n", "no heading\n", "no-title"),
        ("status: accepted\ndate: 2026-01-15\nscope: src/**\n", "# T\n", "bad-scope"),
        ("status: accepted\ndate: 2026-01-15\nscope: ['/etc/**']\n", "# T\n", "bad-scope"),
        ("status: accepted\ndate: 2026-01-15\nscope: ['../x/**']\n", "# T\n", "bad-scope"),
        ("status: accepted\ndate: 2026-01-15\nsupersedes: [x]\n", "# T\n", "bad-field"),
    ],
)
def test_parse_errors(front, body, code):
    with pytest.raises(AdrError) as exc:
        parse_adr(P, doc(front, body))
    assert exc.value.code == code


def test_bad_filename():
    with pytest.raises(AdrError) as exc:
        parse_adr(Path("notes.md"), doc("status: accepted\ndate: 2026-01-15\n"))
    assert exc.value.code == "bad-filename"


def test_no_frontmatter():
    with pytest.raises(AdrError) as exc:
        parse_adr(P, "# T\n")
    assert exc.value.code == "no-frontmatter"


def _adr(front: str):
    return parse_adr(
        Path("0002-x.md"), f"---\nstatus: accepted\ndate: 2026-01-15\n{front}---\n# X\n"
    )


def test_review_keys_are_parsed():
    adr = _adr('review-by: 2027-01-01\nreviewed: 2026-06-01\nrevisit-if: "Postgres 18 ships"\n')
    assert adr.review_by == dt.date(2027, 1, 1)
    assert adr.reviewed == dt.date(2026, 6, 1)
    assert adr.revisit_if == "Postgres 18 ships"


def test_review_keys_default_to_none():
    adr = _adr("")
    assert (adr.review_by, adr.reviewed, adr.revisit_if) == (None, None, None)
    assert adr.baseline == dt.date(2026, 1, 15)


def test_baseline_is_the_later_date():
    assert _adr("reviewed: 2026-06-01\n").baseline == dt.date(2026, 6, 1)
    assert _adr("reviewed: 2025-06-01\n").baseline == dt.date(2026, 1, 15)  # never backwards


@pytest.mark.parametrize(
    ("front", "code"),
    [
        ("review-by: 2026-13-01\n", "bad-date"),
        ("reviewed: soon\n", "bad-date"),
        ("revisit-if: 3\n", "bad-field"),
    ],
)
def test_bad_review_values(front, code):
    with pytest.raises(AdrError) as exc:
        _adr(front)
    assert exc.value.code == code


def test_yaml_with_day_in_text_is_not_date_error():
    # Verify that invalid YAML containing "day" is still reported as no-frontmatter, not bad-date
    with pytest.raises(AdrError) as exc:
        parse_adr(
            P,
            "---\nstatus: accepted\ndate: 2026-01-15\nbad_yaml: [unclosed day\n---\n# X\n",
        )
    assert exc.value.code == "no-frontmatter"


ADR_TOOLS = (
    "# 1. Record architecture decisions\n\nDate: 2016-02-12\n\n"
    "## Status\n\nAccepted\n\n## Context\n"
)


def test_no_frontmatter_hints_status_and_date_from_an_adr_tools_file():
    with pytest.raises(AdrError) as exc:
        parse_adr(Path("0001-x.md"), ADR_TOOLS)
    assert exc.value.code == "no-frontmatter"
    assert "status: accepted" in exc.value.message
    assert "date: 2016-02-12" in exc.value.message


def test_no_frontmatter_hint_survives_crlf():
    with pytest.raises(AdrError) as exc:
        parse_adr(Path("0001-x.md"), ADR_TOOLS.replace("\n", "\r\n"))
    assert "status: accepted" in exc.value.message and "date: 2016-02-12" in exc.value.message


def test_no_frontmatter_hint_uses_placeholders_when_nothing_is_found():
    with pytest.raises(AdrError) as exc:
        parse_adr(Path("0001-x.md"), "# T\n")
    assert "status: <status>" in exc.value.message and "date: <YYYY-MM-DD>" in exc.value.message


def test_no_frontmatter_hint_does_not_suggest_an_unknown_status():
    with pytest.raises(AdrError) as exc:
        parse_adr(Path("0001-x.md"), "# T\n\n## Status\n\nSuperseded by [ADR 5]\n")
    assert "status: <status>" in exc.value.message


def test_broken_frontmatter_keeps_its_own_message():
    with pytest.raises(AdrError) as exc:
        parse_adr(Path("0001-x.md"), "---\nstatus: accepted\n# T\n")
    assert "unterminated" in exc.value.message and "add frontmatter" not in exc.value.message


def test_no_frontmatter_hint_skips_a_bom_prefixed_block_and_an_invalid_date():
    with pytest.raises(AdrError) as exc:
        parse_adr(Path("0001-x.md"), "﻿---\nstatus: accepted\ndate: 2026-01-01\n---\n# T\n")
    assert "add frontmatter" not in exc.value.message
    with pytest.raises(AdrError) as exc:
        parse_adr(Path("0001-x.md"), "# T\n\nDate: 2016-13-45\n\n## Status\n\nProposed\n")
    assert "date: <YYYY-MM-DD>" in exc.value.message
