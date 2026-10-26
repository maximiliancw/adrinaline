---
status: accepted
date: 2026-10-26
---
# Read-only git integration

## Context and Problem Statement

`adr` needs git for the repository root, cross-branch numbering, history and diffs. Committing on the user's behalf would conflict with their own commit workflow.

## Considered Options

* Read-only git
* Optional `--commit`
* No git

## Decision Outcome

Chosen option: "Read-only git", because users and their agents stay in charge of every commit; a test guards against any git write.

### Consequences

* Good, because `adr` never surprises anyone with commits or fetches.
* Bad, because number allocation only sees refs as fresh as the last fetch.
