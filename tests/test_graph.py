import shutil
import subprocess
from pathlib import Path

import pytest

from adrinaline.graph import (
    IMPACT,
    AdrGraph,
    Edge,
    all_nodes,
    graph_data,
    render_dot,
    render_mermaid,
    render_text,
)
from adrinaline.repo import parse_all


def adr(
    number: int, slug: str, title: str, status: str = "accepted", **rel: list[int]
) -> tuple[Path, str]:
    lines = [f"status: {status}", "date: 2026-01-15"]
    lines += [f"{k.replace('_', '-')}: {v}" for k, v in rel.items()]
    return Path(f"d/{number:04d}-{slug}.md"), "---\n" + "\n".join(lines) + f"\n---\n# {title}\n"


def sample() -> AdrGraph:
    return AdrGraph(
        parse_all(
            [
                adr(1, "record-decisions", "Record decisions"),
                adr(2, "use-mysql", "Use MySQL", "superseded", superseded_by=[3]),
                adr(3, "use-postgresql", "Use PostgreSQL", supersedes=[2], depends_on=[1]),
                adr(
                    4,
                    "add-read-replicas",
                    "Add read replicas",
                    "proposed",
                    amends=[3],
                    relates_to=[1],
                ),
            ]
        ).adrs
    )


def test_edges_are_deduplicated_forward_edges():
    assert sample().edges == [
        Edge(3, 2, "supersedes"),
        Edge(3, 1, "depends-on"),
        Edge(4, 3, "amends"),
        Edge(4, 1, "relates-to"),
    ]


def test_related_derives_inverses():
    g = sample()
    assert g.related(3) == {"amended-by": [4], "depends-on": [1], "supersedes": [2]}
    assert g.related(1) == {"dependency-of": [3], "relates-to": [4]}
    assert g.related(2) == {"superseded-by": [3]}


def test_in_force_and_successor():
    g = sample()
    assert [a.number for a in g.in_force()] == [1, 3]
    assert g.successor(2) == 3 and g.successor(3) == 3


def test_missing_targets_render_as_missing():
    g = AdrGraph(parse_all([adr(1, "a", "A", depends_on=[9])]).adrs)
    assert g.label(9) == "0009 (missing)" and g.status(9) == "missing"
    assert g.related(1) == {"depends-on": [9]}


def test_cycle_detection():
    g = sample()
    assert g.cycle("depends-on") is None
    assert g.cycle("depends-on", Edge(1, 3, "depends-on")) is not None


def test_reachable_forward_follows_relates_to_both_ways():
    sub = sample().reachable(3)
    assert sub.nodes == [3, 2, 1, 4]
    assert sub.steps[:3] == [(3, 2, "supersedes"), (3, 1, "depends-on"), (1, 4, "relates-to")]


def test_reachable_reverse_impact_and_depth():
    g = sample()
    assert g.reachable(1, IMPACT, reverse=True).nodes == [1, 3, 4]
    assert g.reachable(1, IMPACT, reverse=True, depth=1).nodes == [1, 3]


SNAPSHOTS = Path(__file__).parent / "snapshots"


def test_text_tree_marks_repeats():
    g = sample()
    assert render_text(g, g.reachable(3)) == (
        "0003 Use PostgreSQL [accepted]\n"
        "  supersedes -> 0002 Use MySQL [superseded]\n"
        "  depends-on -> 0001 Record decisions [accepted]\n"
        "    relates-to -> 0004 Add read replicas [proposed]\n"
        "      amends -> 0003 Use PostgreSQL (see above)"
    )


def test_text_whole_set():
    assert render_text(sample(), None).splitlines()[2:4] == [
        "0003 Use PostgreSQL [accepted]",
        "  supersedes -> 0002 Use MySQL",
    ]


def test_mermaid_and_dot_snapshots():
    g = sample()
    nodes = all_nodes(g)
    assert render_mermaid(g, nodes, g.edges) + "\n" == (SNAPSHOTS / "sample.mmd").read_text()
    assert render_dot(g, nodes, g.edges) + "\n" == (SNAPSHOTS / "sample.dot").read_text()


@pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz not installed")
def test_dot_is_valid_graphviz():
    g = sample()
    proc = subprocess.run(
        ["dot", "-Tsvg"], input=render_dot(g, all_nodes(g), g.edges), capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr


def test_quotes_in_titles_are_escaped():
    g = AdrGraph(parse_all([adr(1, "q", 'Say "hi"')]).adrs)
    assert 'A1["0001 Say #quot;hi#quot;"]' in render_mermaid(g, [1], [])
    assert 'label="0001 Say \\"hi\\""' in render_dot(g, [1], [])


def test_graph_data():
    g = sample()
    data = graph_data(g, [1, 9], [Edge(1, 9, "depends-on")], {1: 0.5})
    assert data == {
        "nodes": [
            {
                "number": 1,
                "id": "0001",
                "title": "Record decisions",
                "status": "accepted",
                "rank": 0.5,
            },
            {"number": 9, "id": "0009", "title": None, "status": "missing", "rank": 0.0},
        ],
        "edges": [{"from": 1, "to": 9, "relation": "depends-on"}],
    }
