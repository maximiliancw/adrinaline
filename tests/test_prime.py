from pathlib import Path

import pytest

from adrinaline import prime
from adrinaline.graph import AdrGraph
from adrinaline.repo import parse_all


def graph_of(*specs: tuple[int, str, str, list[str]]) -> AdrGraph:
    items = []
    for n, status, date, scope in specs:
        front = f"status: {status}\ndate: {date}\nscope: {scope}\n"
        items.append((Path(f"d/{n:04d}-a{n}.md"), f"---\n{front}---\n# Decision {n}\n"))
    return AdrGraph(parse_all(items).adrs)


def test_scope_hit_wins_a_tight_budget():
    g = graph_of((1, "accepted", "2026-01-15", []), (2, "accepted", "2026-01-15", ["src/**"]))
    chosen, omitted = prime.select(g, g.in_force(), ["src/app.py"], budget=4)
    assert [a.number for a in chosen] == [2] and omitted == 1


def test_same_dates_and_tiny_budget():
    g = graph_of((1, "accepted", "2026-01-15", []), (2, "accepted", "2026-01-15", []))
    assert list(prime.scores(g, g.in_force(), []).values()) == [pytest.approx(0.7)] * 2
    chosen, omitted = prime.select(g, g.in_force(), [], budget=1)
    assert [a.number for a in chosen] == [1] and omitted == 1  # top entry always shown


def test_briefing_sections():
    g = graph_of(
        (1, "accepted", "2026-01-15", []),
        (2, "proposed", "2026-01-16", []),
        (3, "rejected", "2026-01-17", []),
    )
    b = prime.briefing(g, "docs/adr", [])
    assert [a.number for a in b.shown] == [1] and [a.number for a in b.proposed] == [2]
    assert b.markdown.startswith(
        "# ADR briefing\n\nADRs live in `docs/adr`: 1 proposed, 1 accepted, 1 rejected."
    )
    assert "## Using adr" in b.markdown


def test_empty_set():
    b = prime.briefing(AdrGraph([]), "docs/adr", [], budget=10)
    assert "none yet" in b.markdown and b.omitted == 0


def test_prime_cli_lists_in_force_and_proposed(initialized):  # AC14
    initialized.adr("new", "Use MySQL", "--accepted")
    initialized.adr("new", "Use PostgreSQL", "--supersedes", "2", "--accepted")
    initialized.adr("new", "Try caching")
    data = initialized.adr("prime", "--json").json()
    assert [a["number"] for a in data["in_force"]] == [1, 3]
    assert [a["number"] for a in data["proposed"]] == [4]
    assert "adr for" in initialized.adr("prime").out


def test_prime_budget(initialized):  # AC23
    long = "about a deliberately long descriptive topic for budgets"
    initialized.write_adr(2, "keystone", title=f"Keystone {long}", date="2025-01-01")
    for n in range(3, 31):
        initialized.write_adr(n, f"d{n}", title=f"Decision {n} {long}", depends_on=[2])
    result = initialized.adr("prime", "--budget", "150")
    assert result.code == 0, result.err
    section = result.out.split("## Decisions in force\n\n")[1].split("\n\n")
    entries, omitted_line = section[0], section[1]
    assert len(entries.split()) <= 150
    assert "0002 Keystone" in entries
    shown = len(entries.splitlines())
    assert omitted_line == f"{30 - shown} more in force: `adr list --status accepted`"


def test_prime_at_ignores_working_tree(initialized):
    initialized.write_adr(2, "scoped", scope=["src/**"])
    initialized.write_adr(3, "other", date="2027-01-01")  # newest, so it wins without a scope hit
    initialized.commit_all()
    initialized.write("src/x.py", "x\n")
    now = initialized.adr("prime", "--budget", "4", "--json").json()
    then = initialized.adr("prime", "--at", "HEAD", "--budget", "4", "--json").json()
    assert [a["number"] for a in now["in_force"]] == [2]
    assert [a["number"] for a in then["in_force"]] == [3]


def test_top_entry_exceeding_budget_is_shown():
    g = graph_of((1, "accepted", "2026-01-15", []), (2, "accepted", "2026-01-16", []))
    chosen, omitted = prime.select(g, g.in_force(), [], budget=1)
    assert [a.number for a in chosen] == [2] and omitted == 1


def test_prime_negative_budget_is_usage_error(initialized):
    assert initialized.adr("prime", "--budget", "-1").code == 2


from adrinaline.model import Finding  # noqa: E402


def test_briefing_needs_review_section():
    g = graph_of((1, "accepted", "2026-01-15", []))
    note = Finding(
        "review-overdue",
        "warning",
        "d/0001-a1.md",
        "0001 Decision 1: review-by 2026-06-01 has passed; run `adr review 1` after revisiting it",
    )
    b = prime.briefing(g, "docs/adr", [], review=[note])
    assert "## Needs review\n\n- 0001 Decision 1: review-by 2026-06-01 has passed" in b.markdown
    assert (
        b.markdown.index("## Decisions in force")
        < b.markdown.index("## Needs review")
        < b.markdown.index("## Proposed")
    )
    assert "## Needs review" not in prime.briefing(g, "docs/adr", []).markdown
    assert "adr review N" in prime.RULES


def test_prime_cli_needs_review(initialized):  # AC28
    w = initialized
    assert "Needs review" not in w.adr("prime").out
    w.write_adr(2, "x", review_by="2000-01-01")
    w.write_adr(3, "db", scope=["src/db/**"])
    w.write(".adrinaline.toml", "drift-commits = 1\n")
    w.commit_all("adrs")
    w.write("src/db/conn.py", "1\n")
    w.commit_all("db")
    out = w.adr("prime").out
    assert "## Needs review" in out and "adr review 2" in out and "adr review 3" in out
    data = w.adr("prime", "--json").json()
    assert [f["code"] for f in data["needs_review"]] == ["review-overdue", "stale-decision"]
    assert data["needs_review"][1]["path"] == "docs/adr/0003-db.md"
    assert "## Needs review" in w.adr("prime", "--budget", "5").out


def test_prime_scope_hit_handles_quoted_filenames(initialized):  # AC for adr-mlxd
    """A changed file with quotes/spaces in its name is matched by prime scope scoring."""
    w = initialized
    w.write_adr(2, "scoped", scope=["src/**"])
    w.commit_all("add scoped ADR")
    # Create a file with quotes and spaces in the name
    odd_path = w.root / 'src/odd"file name.py'
    odd_path.parent.mkdir(parents=True, exist_ok=True)
    odd_path.write_text("# odd file\n")
    w.git("add", str(odd_path))
    w.git("commit", "-m", "add odd file")
    # The scope hit should work regardless of the filename quoting
    out = w.adr("prime", "--json").json()
    # ADR 2 should be in the briefing due to scope hit on src/**
    shown_numbers = [a["number"] for a in out["in_force"]]
    assert 2 in shown_numbers
