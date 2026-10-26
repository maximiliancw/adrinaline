---
status: accepted
date: 2026-10-26
depends-on: [2]
---
# Store only forward relations plus superseded-by

## Context and Problem Statement

Relations between ADRs can be stored on both files or derived from one side.

## Considered Options

* Both sides on disk
* Forward relations only, plus `superseded-by`
* Forward relations only

## Decision Outcome

Chosen option: "Forward relations only, plus `superseded-by`", because the in-memory graph derives inverses, old ADRs stay untouched (fewer merge conflicts), and readers of a superseded ADR still see its successor.

### Consequences

* Good, because adding a relation changes one file.
* Bad, because `amended-by` and `dependency-of` are visible only through `adr`.
