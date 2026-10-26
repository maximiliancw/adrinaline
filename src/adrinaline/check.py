"""Validation rules for `adr check`. Each rule returns Finding objects."""

from collections import defaultdict

from adrinaline.model import Finding
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


def run_checks(s: AdrSet, *, template_exists: bool) -> list[Finding]:
    findings = [*s.problems, *_duplicates(s), *_gaps(s)]
    if not template_exists:
        findings.append(
            Finding("no-template", "warning", "", "template is missing; `adr init` recreates it")
        )
    return sorted(findings, key=lambda f: (f.path, f.code))
