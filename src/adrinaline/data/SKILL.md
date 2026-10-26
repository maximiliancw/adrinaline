---
name: adr
description: Record, find and respect Architecture Decision Records (ADR, decision record, docs/adr) with the `adr` CLI. Use before changing architecture, adding a dependency, changing a public interface, data format or security control, and whenever a task touches files governed by an ADR.
compatibility: requires the adr CLI and git
license: MIT
metadata:
  version: "{version}"
---

# Architecture Decision Records with `adr`

ADRs are Markdown files in the repository (usually `docs/adr/NNNN-slug.md`) with YAML frontmatter. `adr` manages them. Every command accepts `--json`; prefer it when parsing. An installed copy of this skill goes stale after you upgrade adr: reinstall it with `adr skill --install DIR`. Details: `references/frontmatter.md`.

## At the start of a task

1. Run `adr prime` to see the decisions in force. Its sections: decisions in force, proposed ADRs, and short usage rules.
2. Before editing a file, run `adr for <path>` and follow the ADRs it lists. Use `adr show N` to read a whole decision.
3. If a command fails with `no-adr-dir` (exit 3), ask the user before running `adr init`.

```json
{"src/db/conn.py": [{"number": 7, "id": "0007", "title": "Use PostgreSQL", "status": "accepted", "path": "docs/adr/0007-use-postgresql.md", "scope": ["src/db/**"]}]}
```

## Statuses

`proposed`, `accepted`, `rejected`, `deprecated`, `superseded`. `adr new` makes `proposed`; `adr accept N` and `adr reject N` act on proposed; `adr deprecate N` acts on accepted; `adr new "…" --supersedes N` (or `adr supersede OLD --by NEW`) makes an accepted ADR `superseded`. `--supersedes` on a non-accepted ADR needs `--force`.

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

New ADRs start as `proposed`. A human accepts them with `adr accept N`. Do not put `# Title` in the `--body-file` body (adr adds it). Avoid `--edit`: it opens an interactive editor. If you have a question tool, ask through it.

## Accepting a proposed ADR

When the human approves a plan, or you are about to commit a change, and it touches the scope of a proposed ADR (`adr for --all <path>` lists it; plain `adr for` shows only ADRs in force), ask first:

```text
This change relates to the following proposed ADRs:
- 0007 Use PostgreSQL (docs/adr/0007-use-postgresql.md)

Approve status change to accepted? [y/N]
```

N is the number in the filename that `adr new` prints; a fresh proposed ADR only shows up with `adr for --all`. On yes, run `adr accept N` and include the status change in the same commit. On anything else, leave it proposed.

## Changing a decision

Never rewrite the decision of an accepted ADR. Instead:

* Replace it: `adr new "…" --supersedes N`
* Change part of it: `adr new "…" --amends N`
* Relations: `supersedes`, `amends`, `depends-on`, `relates-to`. Add one later with `adr link SRC RELATION DST` (RELATION is `amends`, `depends-on` or `relates-to`), e.g. `adr link NEW depends-on N`.

## Before finishing

Run `adr check`. Fix every error it reports.

## If check fails

Exit codes: 1 `check` found problems, 2 usage error, 3 domain error (e.g. `not-found`, `invalid-transition`, `no-adr-dir`). Errors fail `check`; warnings fail it only with `--strict`. With `--json`, `check` prints `{"ok": bool, "findings": [...]}` and other failures `{"error": {"code": "...", "message": "..."}}`.
