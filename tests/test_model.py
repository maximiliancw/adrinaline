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
