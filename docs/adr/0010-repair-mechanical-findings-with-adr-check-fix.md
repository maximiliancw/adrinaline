---
status: accepted
date: 2026-11-09
scope: [src/adrinaline/fix.py]
depends-on: [3]
---
# Repair mechanical findings with adr check --fix

## Context and Problem Statement

`adr check` reports findings and leaves every repair to the user (SPEC §11: "`adr check --fix` is not in v1"). Some findings have exactly one correct repair that needs no judgement: a missing inverse of `supersedes`, a status that disagrees with `superseded-by`, a snake_case relation key, a deleted template. Doing these by hand is tedious and error-prone, especially after hand-editing frontmatter or merging branches. Should the tool repair them, and where does that write path live?

## Considered Options

- `adr check --fix` repairs a closed list of mechanical codes, then re-checks (this ADR)
- A separate `adr fix` command that repairs and then runs `check`
- No repairs; keep fixing manual

## Decision Outcome

Chosen: `adr check --fix`. Without `--fix`, `check` stays read-only. With it, `check` repairs only these codes, then re-checks and reports what remains; the exit code comes from the remaining findings:

| Code | Repair | Left alone |
|---|---|---|
| `asymmetric-relation` | write the missing inverse (`supersedes` ↔ `superseded-by`) on the other ADR | — |
| `status-mismatch` | set `status: superseded` when `superseded-by` is set; runs after the relation repair | status `superseded` without `superseded-by`: the successor is unknown |
| `unknown-relation-key` | rename the snake_case key to its hyphenated form | the hyphenated key also exists: merging could lose data |
| `no-template` | recreate `.template.md` from the bundled template | — |

Each repair prints `fixed <code> <path>: <what>`; `--json` adds a `fixed` list next to `findings`. Edits go through the existing frontmatter round-trip, so comments and key order survive. Adding a code to the list needs a new ADR that amends this one. The repairs live in their own module, so `check.py` stays read-only.

A separate `adr fix` command was rejected because `check --fix` is the convention agents and linters already know (ruff, eslint), and one command keeps the CI and pre-commit story unchanged. Keeping repairs manual was rejected because the four repairs are deterministic and the manual fix is the same edit every time.

### Consequences

- `check` can write files when, and only when, `--fix` is given; CI and the pre-commit hook keep running it without the flag.
- Repairs touch only ADR frontmatter and the template; git stays read-only (ADR 0004) and the user reviews the result with `git diff`.
- The relation repair writes stored relations only, as ADR 0003 allows.
- No dry run: git shows what changed. Add `--diff` when someone needs to preview without a working tree.
