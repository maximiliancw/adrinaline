"""Decision health: churn over an ADR's scope since its baseline, and the review findings."""

import datetime as dt
from dataclasses import dataclass
from pathlib import PurePosixPath

from adrinaline.git import Commit
from adrinaline.model import Adr, Finding


def _in_scope(file: str, adr: Adr) -> bool:
    return any(PurePosixPath(file).full_match(g) for g in adr.scope)


@dataclass
class Drift:
    adr: Adr
    commits: list[Commit]  # newest first, as git log prints them

    @property
    def files(self) -> list[str]:
        return sorted({f for c in self.commits for f in c.files if _in_scope(f, self.adr)})

    @property
    def last(self) -> Commit | None:
        return self.commits[0] if self.commits else None


def earliest_baseline(adrs: list[Adr]) -> dt.date | None:
    """Start of the one git log call that serves every scoped ADR."""
    return min((adr.baseline for adr in adrs if adr.scope), default=None)


def compute(adrs: list[Adr], commits: list[Commit]) -> list[Drift]:
    """One Drift per ADR with a scope, highest churn first. Churn counts commits whose committer
    date is a later day than the baseline (SPEC §8); ADRs without a scope are skipped."""
    result = []
    for adr in adrs:
        if not adr.scope:
            continue
        hits = [
            c for c in commits if c.date > adr.baseline and any(_in_scope(f, adr) for f in c.files)
        ]
        result.append(Drift(adr, hits))
    return sorted(result, key=lambda d: (-len(d.commits), d.adr.number))


def review_findings(
    adrs: list[Adr], drifts: list[Drift], today: dt.date, threshold: int
) -> list[Finding]:
    """`review-overdue` for every ADR whose review-by has passed; `stale-decision` for every
    drift at or above the threshold (threshold 0 disables it). Order: overdue first, then
    stale in drift order."""
    found = [
        Finding(
            "review-overdue",
            "warning",
            str(adr.path),
            f"{adr.id} {adr.title}: review-by {adr.review_by} has passed; "
            f"run `adr review {adr.number}` after revisiting it",
        )
        for adr in adrs
        if adr.review_by and adr.review_by < today
    ]
    if threshold > 0:
        found += [
            Finding(
                "stale-decision",
                "warning",
                str(d.adr.path),
                f"{d.adr.id} {d.adr.title}: {len(d.commits)} commits touched its scope since "
                f"{d.adr.baseline}; run `adr review {d.adr.number}` after revisiting it",
            )
            for d in drifts
            if len(d.commits) >= threshold
        ]
    return found
