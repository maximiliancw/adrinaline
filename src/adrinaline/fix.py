"""Repairs for mechanical `check` findings (ADR 0010)."""

import datetime as dt
from dataclasses import dataclass

from adrinaline import repo
from adrinaline.check import SNAKE_KEYS
from adrinaline.graph import AdrGraph
from adrinaline.model import Adr, Status
from adrinaline.repo import AdrSet, Location


@dataclass(frozen=True)
class Fix:
    code: str
    path: str
    message: str


def apply(s: AdrSet, loc: Location, today: dt.date) -> list[Fix]:
    """Repair the codes ADR 0010 lists, write the files, return what changed."""
    fixes: list[Fix] = []
    changed: dict[int, Adr] = {}

    def done(adr: Adr, code: str, message: str) -> None:
        changed[id(adr)] = adr
        fixes.append(Fix(code, str(adr.path), message))

    nodes = AdrGraph(s.adrs).nodes
    for adr in s.adrs:
        for name, inverse in (("supersedes", "superseded-by"), ("superseded-by", "supersedes")):
            for n in adr.relations[name]:
                other = nodes.get(n)
                if (
                    other
                    and other.number != adr.number
                    and adr.number not in other.relations[inverse]
                ):
                    repo.set_relation(other, inverse, [*other.relations[inverse], adr.number])
                    done(
                        other,
                        "asymmetric-relation",
                        f"{other.id} {inverse}: {other.relations[inverse]}",
                    )
    for adr in s.adrs:
        if adr.relations["superseded-by"] and adr.status is not Status.SUPERSEDED:
            repo.set_status(adr, Status.SUPERSEDED, today)
            done(adr, "status-mismatch", f"{adr.id} status: superseded")
    for adr in s.adrs:
        for key in [k for k in adr.meta if k in SNAKE_KEYS]:
            new = key.replace("_", "-")
            if new in adr.meta:
                continue
            position = list(adr.meta).index(key)
            adr.meta.insert(position, new, adr.meta.pop(key))
            done(adr, "unknown-relation-key", f"{adr.id} `{key}` -> `{new}`")
    for adr in changed.values():
        repo.save(adr)
    if not loc.template.is_file():
        repo.atomic_write(loc.template, repo.data_text("template.md"))
        fixes.append(Fix("no-template", str(loc.template), "recreated from the bundled template"))
    return fixes
