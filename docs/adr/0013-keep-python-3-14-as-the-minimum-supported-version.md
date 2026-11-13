---
status: accepted
date: 2026-11-14
amends: [2]
---
# Keep Python 3.14 as the minimum supported version

## Context and Problem Statement

ADR 0002 chose "Python 3.14 with uv"; `requires-python` is `>=3.14`. Ticket
adr-j70t asked whether to widen the floor to 3.13, on the grounds that it
grows the install base for `pipx install` users who do not use `uv`.

## Considered Options

* Keep 3.14 as the minimum supported version.
* Widen the floor to 3.13.

## Decision Outcome

Chosen option: "Keep Python 3.14 as the minimum supported version", because
the only version-gated dependency in the code is `PurePath.full_match`
(3.13+, SPEC §3) — nothing requires 3.14 specifically, so 3.13 is technically
feasible but we decline it. Supporting a single interpreter keeps CI to one
Python per OS and the review surface minimal, and the primary install path is
`uv tool install`, where `uv` fetches 3.14 on demand, so the install-base gain
from 3.13 is marginal. No user has requested 3.13.

### Consequences

* Good, because one interpreter to test and support; the SPEC's "Python 3.14+"
  stays true and simple.
* Bad, because a `pipx`-only user whose system tops out at 3.13 must first
  install 3.14 (via `uv` or `pyenv`) before installing `adrinaline`.
