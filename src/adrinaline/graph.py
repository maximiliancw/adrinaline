"""In-memory ADR graph: typed edges, derived inverses, traversal and rendering."""

from collections import defaultdict, deque
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter

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
            if edge.relation == relation:
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
