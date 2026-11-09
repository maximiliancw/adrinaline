---
status: proposed
date: 2026-11-09
scope: [src/adrinaline/cli.py, src/adrinaline/drift.py, src/adrinaline/check.py, src/adrinaline/model.py, src/adrinaline/repo.py, src/adrinaline/graph.py]
amends: [3, 8, 9, 10]
---
# Extend the scopes of ADRs 3, 8, 9 and 10 to their implementing files

## Context and Problem Statement

`adr for PATH` and `adr check --diff` rely on each ADR's `scope`. A docs/code drift review found that four accepted ADRs name fewer files than implement them, so commits to those files pass `check --diff` uncited, and `adr for` stays silent where a decision applies:

- ADR 0003 (stored relations) has no scope. It is implemented in `model.py`, `repo.py`, `graph.py`, `check.py` and `fix.py`.
- ADR 0008 (review dates, scope churn) omits `drift.py` and the `review` and `drift` commands in `cli.py`.
- ADR 0009 (commit trailers) omits the `trace` command in `cli.py`.
- ADR 0010 (`check --fix`) omits the `--fix` wiring in `cli.py`.

ADR 0010 also says "Add `--diff` when someone needs to preview", but `check --diff REF` already means the commit-range check (ADR 0009), so that sentence names a flag that cannot be used for a preview.

Accepted ADRs are never edited (ADR 0001), so the fix is an amending ADR.

## Considered Options

- One amending ADR whose own scope lists the missing files and that corrects the preview note (this ADR)
- One amending ADR per affected decision
- Edit the `scope` fields in place as metadata

## Decision Outcome

Chosen option: one amending ADR. Its scope is the union of the missing files, so `adr for` and `check --diff` now name this ADR, and this ADR names the decisions it carries:

| File | Carries |
|---|---|
| `src/adrinaline/cli.py` | 0008 (`review`, `drift`), 0009 (`trace`), 0010 (`check --fix`) |
| `src/adrinaline/drift.py` | 0008 |
| `src/adrinaline/check.py`, `src/adrinaline/model.py` | 0003 |
| `src/adrinaline/repo.py`, `src/adrinaline/graph.py` | 0003 |

The last consequence of ADR 0010 is replaced by: "No dry run: git shows what changed. A preview flag, if one is ever needed, is `--dry-run`; `--diff` is taken by the commit-range check."

One ADR per decision was rejected because the four changes share one cause and one review. Editing `scope` in place was rejected because scope changes what `check --diff` enforces, which is a decision, not metadata.

### Consequences

* Good, because commits to `cli.py` and `drift.py` now have governing ADRs to cite.
* Good, because the misleading `--diff` sentence is corrected without rewriting ADR 0010.
* Bad, because a reader of `adr for src/adrinaline/cli.py` sees this ADR and must follow its table to the original decision.
* ADRs 0001 to 0006 still carry no scope; widening them is a separate decision.
