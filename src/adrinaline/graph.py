"""In-memory ADR graph: typed edges, derived inverses, traversal and rendering."""

from collections import defaultdict, deque
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from pathlib import PurePosixPath

from adrinaline.model import INVERSE, Adr, Status

FORWARD = ("supersedes", "amends", "depends-on", "relates-to")
ACYCLIC = ("supersedes", "depends-on")
IMPACT = ("depends-on", "amends")


@dataclass(frozen=True)
class Edge:
    src: int
    dst: int
    relation: str


@dataclass
class Subgraph:
    nodes: list[int]
    edges: list[Edge]
    steps: list[tuple[int, int, str]]  # (parent, child, relation as seen from the parent)


class AdrGraph:
    def __init__(self, adrs: list[Adr]) -> None:
        self.adrs = adrs
        self.nodes: dict[int, Adr] = {}
        for adr in adrs:
            self.nodes.setdefault(adr.number, adr)
        edges = [
            Edge(adr.number, n, relation)
            for adr in adrs
            for relation in FORWARD
            for n in adr.relations.get(relation, [])
        ]
        edges += [
            Edge(n, adr.number, "supersedes")
            for adr in adrs
            for n in adr.relations.get("superseded-by", [])
        ]
        self.edges = list(dict.fromkeys(edges))

    def rank(
        self, damping: float = 0.85, tolerance: float = 1e-9, max_iterations: int = 100
    ) -> dict[int, float]:
        nodes = sorted(self.nodes)
        if not nodes:
            return {}
        size = len(nodes)
        targets: dict[int, list[int]] = {n: [] for n in nodes}
        for edge in self.edges:
            if edge.src not in targets or edge.dst not in targets:
                continue
            if edge.relation in IMPACT:
                targets[edge.src].append(edge.dst)
            elif edge.relation == "relates-to":
                targets[edge.src].append(edge.dst)
                targets[edge.dst].append(edge.src)
        ranks = dict.fromkeys(nodes, 1 / size)
        for _ in range(max_iterations):
            dangling = sum(ranks[n] for n in nodes if not targets[n])
            fresh = dict.fromkeys(nodes, (1 - damping) / size + damping * dangling / size)
            for n in nodes:
                for target in targets[n]:
                    fresh[target] += damping * ranks[n] / len(targets[n])
            change = sum(abs(fresh[n] - ranks[n]) for n in nodes)
            ranks = fresh
            if change < tolerance:
                break
        return ranks

    def label(self, number: int) -> str:
        adr = self.nodes.get(number)
        return f"{number:04d} {adr.title}" if adr else f"{number:04d} (missing)"

    def status(self, number: int) -> str:
        adr = self.nodes.get(number)
        return adr.status.value if adr else "missing"

    def related(self, number: int) -> dict[str, list[int]]:
        found: dict[str, set[int]] = defaultdict(set)
        for edge in self.edges:
            if edge.src == number:
                found[edge.relation].add(edge.dst)
            if edge.dst == number:
                found[INVERSE[edge.relation]].add(edge.src)
        return {name: sorted(numbers) for name, numbers in sorted(found.items())}

    def in_force(self) -> list[Adr]:
        return [
            adr
            for number, adr in sorted(self.nodes.items())
            if adr.status is Status.ACCEPTED and not self.related(number).get("superseded-by")
        ]

    def successor(self, number: int) -> int:
        seen = {number}
        while successors := self.related(number).get("superseded-by"):
            number = successors[-1]
            if number in seen:
                break
            seen.add(number)
        return number

    def cycle(self, relation: str, extra: Edge | None = None) -> list[int] | None:
        sorter: TopologicalSorter[int] = TopologicalSorter()
        for edge in [*self.edges, *([extra] if extra else [])]:
            if edge.relation == relation and edge.src != edge.dst:
                sorter.add(edge.src, edge.dst)
        try:
            sorter.prepare()
        except CycleError as exc:
            return list(exc.args[1])
        return None

    def reachable(
        self,
        start: int,
        relations: tuple[str, ...] = FORWARD,
        *,
        reverse: bool = False,
        depth: int | None = None,
    ) -> Subgraph:
        sub = Subgraph([start], [], [])
        seen = {start}
        queue = deque([(start, 0)])
        while queue:
            current, level = queue.popleft()
            if depth is not None and level >= depth:
                continue
            for edge in self.edges:
                if edge.relation not in relations or edge in sub.edges:
                    continue
                ahead, behind = (edge.src, edge.dst) if reverse else (edge.dst, edge.src)
                if behind == current:
                    child, name = ahead, INVERSE[edge.relation] if reverse else edge.relation
                elif edge.relation == "relates-to" and ahead == current:
                    child, name = behind, "relates-to"
                else:
                    continue
                sub.edges.append(edge)
                sub.steps.append((current, child, name))
                if child not in seen:
                    seen.add(child)
                    sub.nodes.append(child)
                    queue.append((child, level + 1))
        return sub

    def governing(self, path: str, *, include_proposed: bool = False) -> list[Adr]:
        candidates = self.in_force()
        if include_proposed:
            candidates += [a for _, a in sorted(self.nodes.items()) if a.status is Status.PROPOSED]
        target = PurePosixPath(path)
        return [adr for adr in candidates if any(target.full_match(g) for g in adr.scope)]


_FILL = {
    "proposed": "fill:#fff4cc",
    "accepted": "fill:#d9f2d9",
    "rejected": "fill:#f2d9d9",
    "deprecated": "fill:#e6e6e6",
    "superseded": "fill:#e6e6e6,stroke-dasharray:4 2",
    "missing": "fill:#ffffff,stroke-dasharray:2 2",
}


def all_nodes(graph: AdrGraph) -> list[int]:
    return sorted({*graph.nodes, *(e.src for e in graph.edges), *(e.dst for e in graph.edges)})


def render_text(graph: AdrGraph, sub: Subgraph | None, edges: list[Edge] | None = None) -> str:
    if sub is None:
        lines: list[str] = []
        for number in sorted(graph.nodes):
            lines.append(f"{graph.label(number)} [{graph.status(number)}]")
            lines += [
                f"  {e.relation} -> {graph.label(e.dst)}"
                for e in (graph.edges if edges is None else edges)
                if e.src == number
            ]
        return "\n".join(lines)
    children: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for parent, child, relation in sub.steps:
        children[parent].append((relation, child))
    root = sub.nodes[0]
    lines = [f"{graph.label(root)} [{graph.status(root)}]"]
    seen = {root}

    def walk(number: int, depth: int) -> None:
        for relation, child in children[number]:
            repeat = child in seen
            suffix = " (see above)" if repeat else f" [{graph.status(child)}]"
            lines.append(f"{'  ' * depth}{relation} -> {graph.label(child)}{suffix}")
            if not repeat:
                seen.add(child)
                walk(child, depth + 1)

    walk(root, 1)
    return "\n".join(lines)


def render_mermaid(graph: AdrGraph, nodes: list[int], edges: list[Edge]) -> str:
    lines = ["flowchart LR"]
    for n in nodes:
        label = graph.label(n).replace('"', "#quot;")
        lines.append(f'  A{n}["{label}"]:::{graph.status(n)}')
    for e in edges:
        arrow = "---" if e.relation == "relates-to" else "-->"
        lines.append(f"  A{e.src} {arrow}|{e.relation}| A{e.dst}")
    lines += [f"  classDef {status} {style}" for status, style in _FILL.items()]
    return "\n".join(lines)


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_dot(graph: AdrGraph, nodes: list[int], edges: list[Edge]) -> str:
    lines = ["digraph adr {", "  rankdir=LR;", '  node [shape=box, style="rounded,filled"];']
    for n in nodes:
        fill = _FILL[graph.status(n)].split(",")[0].removeprefix("fill:")
        lines.append(f"  n{n} [label={_quote(graph.label(n))}, fillcolor={_quote(fill)}];")
    for e in edges:
        extra = ", dir=none" if e.relation == "relates-to" else ""
        lines.append(f"  n{e.src} -> n{e.dst} [label={_quote(e.relation)}{extra}];")
    lines.append("}")
    return "\n".join(lines)


def graph_data(
    graph: AdrGraph,
    nodes: list[int],
    edges: list[Edge],
    ranks: dict[int, float] | None = None,
) -> dict:
    node_rows = []
    for n in nodes:
        adr = graph.nodes.get(n)
        row = {
            "number": n,
            "id": f"{n:04d}",
            "title": adr.title if adr else None,
            "status": graph.status(n),
        }
        if ranks is not None:
            row["rank"] = ranks.get(n, 0.0)
        node_rows.append(row)
    return {
        "nodes": node_rows,
        "edges": [{"from": e.src, "to": e.dst, "relation": e.relation} for e in edges],
    }
