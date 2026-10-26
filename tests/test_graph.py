from pathlib import Path

from adrinaline.graph import IMPACT, AdrGraph, Edge
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
