"""Validation rules for `adr check`. Each rule returns Finding objects."""

from collections import defaultdict
from pathlib import PurePosixPath

from adrinaline.graph import ACYCLIC, AdrGraph
from adrinaline.model import STORED_RELATIONS, Finding, Status
from adrinaline.repo import AdrSet

SNAKE_KEYS = {"superseded_by", "depends_on", "relates_to", "amended_by", "dependency_of"}


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


def _gaps(s: AdrSet, taken_elsewhere: set[int]) -> list[Finding]:
    return [
        Finding("number-gap", "warning", "", f"{n:04d} is missing")
        for n in range(1, max(s.numbers, default=0))
        if n not in s.numbers and n not in taken_elsewhere
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


def _unknown_keys(s: AdrSet) -> list[Finding]:
    return [
        Finding(
            "unknown-relation-key",
            "warning",
            str(adr.path),
            f"`{key}` is ignored; use `{key.replace('_', '-')}`",
        )
        for adr in s.adrs
        for key in adr.meta
        if key in SNAKE_KEYS
    ]


def _scopes(
    s: AdrSet, graph: AdrGraph, tracked: list[str] | None, changed: list[str] | None
) -> list[Finding]:
    found: list[Finding] = []
    if tracked is not None:
        paths = [PurePosixPath(f) for f in tracked]
        for adr in s.adrs:
            for glob in adr.scope:
                if not any(p.full_match(glob) for p in paths):
                    found.append(
                        Finding(
                            "scope-matches-nothing",
                            "warning",
                            str(adr.path),
                            f"{adr.id}: scope {glob!r} matches no file",
                        )
                    )
    for path in changed or []:
        if hits := graph.governing(path):
            names = ", ".join(f"{a.id} {a.title}" for a in hits)
            found.append(
                Finding(
                    "scoped-change",
                    "warning",
                    path,
                    f"{path} is governed by {names}; review before merging",
                )
            )
    return found


def run_checks(
    s: AdrSet,
    *,
    template_exists: bool,
    tracked: list[str] | None = None,
    changed: list[str] | None = None,
    taken_elsewhere: set[int] | None = None,
) -> list[Finding]:
    graph = AdrGraph(s.adrs)
    findings = [
        *s.problems,
        *_duplicates(s),
        *_gaps(s, taken_elsewhere or set()),
        *_relations(s, graph),
        *_unknown_keys(s),
        *_scopes(s, graph, tracked, changed),
    ]
    if not template_exists:
        findings.append(
            Finding("no-template", "warning", "", "template is missing; `adr init` recreates it")
        )
    return sorted(findings, key=lambda f: (f.path, f.code))
