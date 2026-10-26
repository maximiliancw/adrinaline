---
name: adr
description: Record, find and respect Architecture Decision Records with the `adr` CLI. Use before changing architecture, adding a dependency, changing a public interface, data format or security control, and whenever a task touches files governed by an ADR.
---

# Architecture Decision Records with `adr`

ADRs are Markdown files in the repository (usually `docs/adr/NNNN-slug.md`) with YAML frontmatter. `adr` manages them. Every command accepts `--json`.

## At the start of a task

1. Run `adr prime` to see the decisions in force.
2. Before editing a file, run `adr for <path>` and follow the ADRs it lists.

## When to write an ADR

Write one for decisions that are expensive to reverse: architecture, frameworks and dependencies, data formats and storage, public interfaces, security and compliance controls. Do not write one for routine implementation choices.

## Writing one

Set `--scope GLOB` (repeatable, repository-relative) so `adr for <path>` finds the ADR.

```bash
adr new "Use PostgreSQL for persistence" --tag storage --scope "src/db/**" --body-file - <<'EOF'
## Context and Problem Statement

…

## Considered Options

* PostgreSQL
* SQLite

## Decision Outcome

Chosen option: "PostgreSQL", because …

### Consequences

* Good, because …
* Bad, because …
EOF
```

New ADRs start as `proposed`. A human accepts them with `adr accept N`.

## Accepting a proposed ADR

When the human approves a plan, or you are about to commit a change, and it touches the scope of a proposed ADR (`adr for --all <path>` lists it; plain `adr for` shows only ADRs in force), ask first:

```text
This change relates to the following proposed ADRs:
- 0007 Use PostgreSQL (docs/adr/0007-use-postgresql.md)

Approve status change to accepted? [y/N]
```

On yes, run `adr accept N` and include the status change in the same commit. On anything else, leave it proposed.

## Changing a decision

Never rewrite the decision of an accepted ADR. Instead:

* Replace it: `adr new "…" --supersedes N`
* Change part of it: `adr new "…" --amends N`
* Record a prerequisite or a related decision: `adr link NEW depends-on N`, `adr link NEW relates-to N`

## Before finishing

Run `adr check`. Fix every error it reports.
