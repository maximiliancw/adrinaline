"""Validation rules for `adr check`. Each rule returns Finding objects."""

import datetime as dt
import re
from collections import defaultdict
from pathlib import PurePosixPath

from adrinaline import __version__, drift
from adrinaline.git import Commit
from adrinaline.graph import ACYCLIC, AdrGraph
from adrinaline.model import STORED_RELATIONS, Adr, Finding, Status
from adrinaline.repo import AdrSet

SNAKE_KEYS = {
    "superseded_by",
    "depends_on",
    "relates_to",
    "review_by",
    "revisit_if",
}


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
    """Relation findings: self-relation, dangling-relation, asymmetric-relation, cycle, and also
    status-mismatch (`superseded-by` set but status not superseded, or the reverse)."""
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


def _trailers(graph: AdrGraph, commits: list[Commit]) -> tuple[list[Finding], set[str]]:
    """uncited-change and exempt-change for each commit touching governed files, plus the files
    whose every touching commit cites an ADR governing that file or is exempt (SPEC §11, §13)."""
    found: list[Finding] = []
    passed: dict[str, bool] = {}
    gov: dict[str, list[Adr]] = {}  # governing() rescans every ADR; a file recurs across commits
    for c in commits:
        for f in c.files:
            if f not in gov:
                gov[f] = graph.governing(f)
        governed = {f: gov[f] for f in c.files if gov[f]}
        if not governed:
            continue
        adrs = {a.number for hits in governed.values() for a in hits}
        cited = not adrs.isdisjoint(c.adrs)
        for f, hits in governed.items():  # a file passes only by citing an ADR governing it
            ok = c.exempt is not None or not {a.number for a in hits}.isdisjoint(c.adrs)
            passed[f] = passed.get(f, True) and ok
        if cited:
            continue
        path, head = next(iter(governed)), f"{c.sha[:8]} {c.subject!r}"
        if c.exempt is not None:
            found.append(Finding("exempt-change", "note", path, f"{head} is exempt: {c.exempt}"))
            continue
        names = ", ".join(graph.label(n) for n in sorted(adrs))
        found.append(
            Finding(
                "uncited-change",
                "warning",
                path,
                f"{head} changes files governed by {names} but cites none; "
                f"add the trailer `ADR: {min(adrs)}` or `ADR-Exempt: <reason>`",
            )
        )
    return found, {f for f, ok in passed.items() if ok}


def _release(version: str | None) -> str | None:
    """Leading numeric segments: a dev build 0.3.1.dev16+gabc counts as 0.3.1."""
    match = re.match(r"\d+(\.\d+)*", version or "")
    return match[0] if match else None


def _stale_skills(skills: dict[str, str | None]) -> list[Finding]:
    return [
        Finding(
            "stale-skill",
            "warning",
            f"{d}/SKILL.md",
            f"installed skill is version {version or 'unknown'}, adr is {__version__}; "
            f"reinstall with `adr skill --install {d}`",
        )
        for d, version in skills.items()
        # "{version}" unfilled: installed by `npx skills` or the plugin, which update it themselves
        if version != "{version}" and _release(version) != _release(__version__)
    ]


def run_checks(
    s: AdrSet,
    *,
    template_exists: bool,
    tracked: list[str] | None = None,
    changed: list[str] | None = None,
    taken_elsewhere: set[int] | None = None,
    today: dt.date | None = None,
    commits: list[Commit] | None = None,
    drift_commits: int = 0,
    range_commits: list[Commit] | None = None,
    uncommitted: list[str] | None = None,
    skills: dict[str, str | None] | None = None,
) -> list[Finding]:
    """Run every rule and return the findings sorted by (path, code).

    Optional inputs switch rules on: `tracked` (files in the repo) enables `scope-matches-nothing`;
    `changed` (files changed against a base) enables `scoped-change`, minus files whose commits in
    `range_commits` cite or exempt the ADR (unless still in `uncommitted`); `skills` maps an
    installed skill dir to its version; `taken_elsewhere` numbers are not reported as gaps.

    `commits` feeds `stale-decision`. None means no git history was read: the threshold is forced
    to 0, which disables the rule. `[]` means history was read and found nothing (or the rule was
    disabled upstream); the threshold stays, but no ADR has churn, so the result is the same.
    `review-overdue` does not depend on `commits`.
    """
    graph = AdrGraph(s.adrs)
    cited, traced = _trailers(graph, range_commits or [])
    traced -= set(uncommitted or [])
    if changed is not None:
        changed = [p for p in changed if p not in traced]
    in_force = graph.in_force()
    findings = [
        *s.problems,
        *_duplicates(s),
        *_gaps(s, taken_elsewhere or set()),
        *_relations(s, graph),
        *_unknown_keys(s),
        *_scopes(s, graph, tracked, changed),
        *_stale_skills(skills or {}),
        *cited,
        *drift.review_findings(
            in_force,
            drift.compute(in_force, commits or []),
            today or dt.date.today(),
            drift_commits if commits is not None else 0,
        ),
    ]
    if not template_exists:
        findings.append(
            Finding("no-template", "warning", "", "template is missing; `adr init` recreates it")
        )
    return sorted(findings, key=lambda f: (f.path, f.code))
