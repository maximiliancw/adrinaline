import datetime as dt
import stat
from pathlib import Path

import pytest

from adrinaline import repo
from adrinaline.model import AdrError, Status


def test_slugify():
    assert repo.slugify("Use PostgreSQL 16!") == "use-postgresql-16"
    assert repo.slugify("Über-Caching für APIs") == "uber-caching-fur-apis"
    assert repo.slugify("???") == "untitled"


def test_locate_outside_git_uses_cwd(tmp_path):
    loc = repo.locate(tmp_path.resolve(), {})
    assert loc.root is None
    assert loc.dir == tmp_path.resolve() / "docs" / "adr"
    assert loc.template == loc.dir / ".template.md"


def test_locate_template_from_config(tmp_path):
    root = tmp_path.resolve()
    (root / ".adrinaline.toml").write_text('dir = "decisions"\ntemplate = "tpl.md"\n')
    loc = repo.locate(root, {})
    assert loc.dir == root / "decisions" and loc.template == root / "tpl.md"


def test_parse_all_collects_problems():
    good = "---\nstatus: accepted\ndate: 2026-01-15\n---\n# A\n"
    s = repo.parse_all(
        [
            (Path("d/0001-a.md"), good),
            (Path("d/0002-b.md"), "no frontmatter"),
            (Path("d/notes.txt"), "x"),
            (Path("d/README.md"), "# readme"),
            (Path("d/.template.md"), "x"),
        ]
    )
    assert [a.number for a in s.adrs] == [1]
    assert sorted(f.code for f in s.problems) == ["bad-filename", "no-frontmatter"]
    assert s.numbers == {1, 2}


def test_resolve():
    good = "---\nstatus: accepted\ndate: 2026-01-15\n---\n# A\n"
    adrs = repo.parse_all(
        [(Path("d/0001-use-postgres.md"), good), (Path("d/0002-use-postgis.md"), good)]
    ).adrs
    assert repo.resolve(adrs, " 001 ").number == 1
    assert repo.resolve(adrs, "PostGIS").number == 2
    with pytest.raises(AdrError) as exc:
        repo.resolve(adrs, "use-post")
    assert exc.value.code == "ambiguous"
    with pytest.raises(AdrError) as exc:
        repo.resolve(adrs, "9")
    assert exc.value.code == "not-found"


def test_render_new_replaces_body_and_merges_tags():
    template = "---\nstatus: proposed\ndate: YYYY-MM-DD\ntags: [team]\n---\n# {title}\n\n## Old\n"
    text = repo.render_new(
        template, "Use X", Status.ACCEPTED, dt.date(2026, 1, 15), "New body\n", ["db"]
    )
    assert text == (
        "---\nstatus: accepted\ndate: 2026-01-15\ntags: [db, team]\n---\n# Use X\n\nNew body\n"
    )


def test_create_file_skips_taken_numbers(tmp_path):
    (tmp_path / "0003-other.md").write_text("x")
    path = repo.create_file(tmp_path, 3, "mine", "text")
    assert path.name == "0004-mine.md" and path.read_text() == "text"


def test_transition_rules():
    good = "---\nstatus: proposed\ndate: 2026-01-15\n---\n# A\n"
    adr = repo.parse_all([(Path("d/0001-a.md"), good)]).adrs[0]
    with pytest.raises(AdrError) as exc:
        repo.transition(adr, Status.SUPERSEDED, today=dt.date(2026, 2, 1))
    assert exc.value.code == "invalid-transition"
    repo.transition(adr, Status.ACCEPTED, today=dt.date(2026, 2, 1))
    assert adr.status is Status.ACCEPTED and adr.meta["date"] == dt.date(2026, 2, 1)


def test_atomic_write_preserves_mode(tmp_path):
    target = tmp_path / "a.md"
    target.write_text("old")
    target.chmod(0o644)
    repo.atomic_write(target, "new")
    assert target.read_text() == "new"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_resolve_non_ascii_digit_falls_back_to_slug():
    with pytest.raises(AdrError) as exc:
        repo.resolve([], "²")
    assert exc.value.code == "not-found"
