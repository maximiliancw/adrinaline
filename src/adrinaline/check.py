"""Validation rules for `adr check`. Each rule returns Finding objects."""

from collections import defaultdict

from adrinaline.graph import ACYCLIC, AdrGraph
from adrinaline.model import STORED_RELATIONS, Finding, Status
from adrinaline.repo import AdrSet


def _duplicates(s: AdrSet) -> list[Finding]:
    groups = defaultdict(list)
    for adr in s.adrs:
        groups[adr.number].append(adr)
    return [
        Finding(
            "duplicate-number",
            "error",
            str(adr.path),
            f"{adr.id} is used by {', '.join(a.path.name for a in group)}; fix with `adr renumber`",
        )
        for group in groups.values()
        if len(group) > 1
        for adr in group
    ]


def _gaps(s: AdrSet) -> list[Finding]:
    return [
        Finding("number-gap", "warning", "", f"{n:04d} is missing")
        for n in range(1, max(s.numbers, default=0))
        if n not in s.numbers
    ]


def _relations(s: AdrSet, graph: AdrGraph) -> list[Finding]:
    found: list[Finding] = []
    for adr in s.adrs:
        path = str(adr.path)
        for name in STORED_RELATIONS:
            for n in adr.relations[name]:
                if n == adr.number:
                    found.append(Finding("self-relation", "error", path, f"{adr.id} {name} itself"))
                elif n not in graph.nodes:
                    found.append(
                        Finding(
                            "dangling-relation",
                            "error",
                            path,
                            f"{adr.id} {name} {n:04d}, which does not exist",
                        )
                    )
        for name, inverse in (("supersedes", "superseded-by"), ("superseded-by", "supersedes")):
            for n in adr.relations[name]:
                other = graph.nodes.get(n)
                if (
                    other
                    and other.number != adr.number
                    and adr.number not in other.relations[inverse]
                ):
                    found.append(
                        Finding(
                            "asymmetric-relation",
                            "error",
                            path,
                            f"{adr.id} {name} {other.id}, but {other.id} has no "
                            f"{inverse}: [{adr.number}]",
                        )
                    )
        if bool(adr.relations["superseded-by"]) != (adr.status is Status.SUPERSEDED):
            found.append(
                Finding(
                    "status-mismatch",
                    "error",
                    path,
                    f"{adr.id}: status {adr.status} does not match superseded-by "
                    f"{adr.relations['superseded-by']}",
                )
            )
    for relation in ACYCLIC:
        if cycle := graph.cycle(relation):
            chain = " -> ".join(f"{n:04d}" for n in cycle)
            found.append(Finding("cycle", "error", "", f"{relation} cycle: {chain}"))
    return found


def run_checks(s: AdrSet, *, template_exists: bool) -> list[Finding]:
    findings = [*s.problems, *_duplicates(s), *_gaps(s), *_relations(s, AdrGraph(s.adrs))]
    if not template_exists:
        findings.append(
            Finding("no-template", "warning", "", "template is missing; `adr init` recreates it")
        )
    return sorted(findings, key=lambda f: (f.path, f.code))
