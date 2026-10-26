from pathlib import Path

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
    assert set(prime.scores(g, g.in_force(), []).values()) == {0.7}
    assert prime.select(g, g.in_force(), [], budget=1) == ([], 2)


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
    initialized.write_adr(3, "other", date="2026-06-01")  # newer, so it wins without a scope hit
    initialized.commit_all()
    initialized.write("src/x.py", "x\n")
    now = initialized.adr("prime", "--budget", "4", "--json").json()
    then = initialized.adr("prime", "--at", "HEAD", "--budget", "4", "--json").json()
    assert [a["number"] for a in now["in_force"]] == [2]
    assert [a["number"] for a in then["in_force"]] == [3]
