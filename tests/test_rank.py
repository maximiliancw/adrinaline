from pathlib import Path

import pytest

from adrinaline.graph import AdrGraph
from adrinaline.repo import parse_all


def make(rel_by_number: dict[int, dict[str, list[int]]]) -> AdrGraph:
    items = []
    for n, rel in rel_by_number.items():
        lines = ["status: accepted", "date: 2026-01-15"] + [f"{k}: {v}" for k, v in rel.items()]
        items.append((Path(f"d/{n:04d}-a{n}.md"), "---\n" + "\n".join(lines) + f"\n---\n# A{n}\n"))
    return AdrGraph(parse_all(items).adrs)


def test_rank_favours_keystones():
    g = make(
        {
            1: {},
            2: {},
            3: {"depends-on": [2]},
            4: {"depends-on": [2]},
            5: {"amends": [2], "relates-to": [1]},
        }
    )
    ranks = g.rank()
    assert max(ranks, key=lambda n: ranks[n]) == 2
    assert sum(ranks.values()) == pytest.approx(1.0, abs=1e-6)


def test_supersedes_passes_no_weight():
    g = make({1: {}, 2: {"supersedes": [1]}})
    ranks = g.rank()
    assert ranks[1] == pytest.approx(ranks[2])


def test_rank_edge_cases():
    assert AdrGraph([]).rank() == {}
    ranks = make({1: {"depends-on": [9]}}).rank()
    assert ranks == {1: pytest.approx(1.0)}


def test_graph_rank_cli(initialized):  # AC22
    for n in range(2, 6):
        initialized.write_adr(n, f"a{n}")
    for n in (3, 4, 5):
        initialized.adr("link", str(n), "depends-on", "2")
    data = initialized.adr("graph", "--rank", "--json").json()
    assert data["nodes"][0]["number"] == 2
    assert sum(node["rank"] for node in data["nodes"]) == pytest.approx(1.0, abs=1e-6)
    assert initialized.adr("graph", "--rank").out.splitlines()[0].endswith("0002 A2 [accepted]")


def test_graph_rank_honours_selection(initialized):
    for n in range(2, 6):
        initialized.write_adr(n, f"a{n}")
    initialized.adr("link", "3", "depends-on", "2")
    initialized.adr("link", "4", "depends-on", "2")
    data = initialized.adr("graph", "3", "--rank", "--json").json()
    assert [n["number"] for n in data["nodes"]] == [2, 3]
    assert initialized.adr("graph", "--rank", "--format", "mermaid").code == 2
