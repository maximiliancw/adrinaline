---
status: accepted
date: 2026-11-09
tags: [process]
scope: [src/adrinaline/check.py, src/adrinaline/git.py]
depends-on: [4]
---
# Cite ADRs in commit trailers

## Context and Problem Statement

`adr check --diff` reports which changed files an ADR governs, but nothing records whether the author actually consulted that ADR. Reviewers cannot tell a change that followed a decision from one that ignored it, and an ADR's history of applications is invisible. How should a change declare the decisions it follows, so the tool can check it deterministically from git alone?

## Considered Options

- Git trailers `ADR: N` and `ADR-Exempt: reason` in the commit message (this ADR)
- A tag in the commit subject, for example `feat(db)[ADR-7]: …`
- A section in the pull or merge request description
- A sidecar file mapping commits to ADRs

## Decision Outcome

Chosen: commit trailers. `ADR:` holds one or more ADR numbers (`ADR: 7`, `ADR: 0007, 0012`) and may repeat; `ADR-Exempt:` holds a free-text reason. They are read with git's own trailer parser (`%(trailers:key=…)`), never written by the tool. `adr trace REF` lists the commits citing an ADR. `adr check --diff REF` judges every non-merge commit in `REF..HEAD` that touches a file governed by an ADR in force: citing one of those ADRs passes, `ADR-Exempt` is reported as an `exempt-change` note, anything else is an `uncited-change` warning. A changed file whose commits all cite an ADR governing it or are exempt, and that has no uncommitted change, no longer raises `scoped-change`, so the strict CI gate passes for traced work and fails for untraced work.

A subject tag was rejected because it competes with Conventional Commits (ADR 0006) for the subject line. A request description is lost with the hosting platform and invisible to `git log`. A sidecar file needs a write per commit and drifts from history.

### Consequences

- Traceability works offline, survives any clone and needs no hosting API.
- Squash merges keep the trailers only if the squash message carries them; rebase and merge commits keep them as written.
- Citing an unrelated ADR does not satisfy the check, so the trailer must name a decision that governs the touched files.
- Uncommitted changes cannot carry a trailer and are judged only by `scoped-change`.
- Git stays read-only (ADR 0004).
