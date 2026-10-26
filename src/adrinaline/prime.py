"""Agent briefing for `adr prime`: decisions in force, proposals and usage rules."""
# ruff: noqa: E501

import heapq
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath

from adrinaline.graph import AdrGraph
from adrinaline.model import Adr, Status

RULES = """\
- Before changing code, run `adr for <path>` and follow the ADRs it lists.
- Write an ADR for decisions that are expensive to reverse: architecture, dependencies, data formats, public interfaces, security. Not for routine choices.
- New ADR: `adr new "Title" --scope GLOB --body-file -` (repeat --scope per governed path glob, repository-relative) with Context and Problem Statement, Considered Options, Decision Outcome and Consequences on stdin.
- New ADRs start as `proposed`; only a human accepts them, so ask before running `adr accept N`.
- Never rewrite an accepted decision: `adr new "…" --supersedes N` replaces it, `adr new "…" --amends N` changes part of it.
- Look things up: `adr show N`, `adr list --status accepted`, `adr graph N`, `adr graph N --reverse`.
- Run `adr check` before you finish. Every command accepts `--json`."""


def _words(text: str) -> int:
    return len(text.split())


def entry(graph: AdrGraph, adr: Adr) -> str:
    related = graph.related(adr.number)
    links = "; ".join(
        f"{name} " + ", ".join(f"{n:04d}" for n in related[name])
        for name in ("depends-on", "amends")
        if related.get(name)
    )
    tags = f" [{', '.join(adr.tags)}]" if adr.tags else ""
    return f"- {adr.id} {adr.title}{tags}" + (f" ({links})" if links else "")


def scores(graph: AdrGraph, adrs: list[Adr], changed: list[str]) -> dict[int, float]:
    ranks = graph.rank()
    top = max(ranks.values(), default=0.0) or 1.0
    days = [adr.date.toordinal() for adr in adrs]
    low, high = min(days, default=0), max(days, default=0)
    paths = [PurePosixPath(p) for p in changed]
    result: dict[int, float] = {}
    for adr in adrs:
        hit = any(p.full_match(glob) for p in paths for glob in adr.scope)
        recency = (adr.date.toordinal() - low) / (high - low) if high > low else 1.0
        result[adr.number] = 0.5 * ranks.get(adr.number, 0.0) / top + 0.3 * hit + 0.2 * recency
    return result


def select(
    graph: AdrGraph, adrs: list[Adr], changed: list[str], budget: int
) -> tuple[list[Adr], int]:
    points = scores(graph, adrs, changed)
    heap = [(-points[adr.number], adr.number, i) for i, adr in enumerate(adrs)]
    heapq.heapify(heap)
    chosen: list[Adr] = []
    used = 0
    while heap:
        _, _, i = heapq.heappop(heap)
        cost = _words(entry(graph, adrs[i]))
        if not chosen or used + cost <= budget:
            chosen.append(adrs[i])
            used += cost
    chosen.sort(key=lambda adr: adr.number)
    return chosen, len(adrs) - len(chosen)


@dataclass
class Briefing:
    markdown: str
    shown: list[Adr]
    omitted: int
    proposed: list[Adr]
    counts: dict[str, int]


def briefing(
    graph: AdrGraph, dir_label: str, changed: list[str], budget: int | None = None
) -> Briefing:
    in_force = graph.in_force()
    proposed = [adr for _, adr in sorted(graph.nodes.items()) if adr.status is Status.PROPOSED]
    if budget is None:
        shown, omitted = in_force, 0
    else:
        shown, omitted = select(graph, in_force, changed, budget)
    counter = Counter(adr.status.value for adr in graph.adrs)
    counts = {s.value: counter[s.value] for s in Status if counter[s.value]}
    summary = ", ".join(f"{n} {status}" for status, n in counts.items()) or "none yet"
    parts = [
        "# ADR briefing",
        f"ADRs live in `{dir_label}`: {summary}.",
        "## Decisions in force",
        "\n".join(entry(graph, adr) for adr in shown) or "None.",
    ]
    if omitted:
        parts.append(f"{omitted} more in force: `adr list --status accepted`")
    parts += [
        "## Proposed",
        "\n".join(entry(graph, adr) for adr in proposed) or "None.",
        "## Using adr",
        RULES,
    ]
    return Briefing("\n\n".join(parts), shown, omitted, proposed, counts)
