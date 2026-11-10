---
status: accepted
date: 2026-11-10
scope: [docs/adr/**, pyproject.toml, src/adrinaline/cli.py, src/adrinaline/output.py, src/adrinaline/prime.py, src/adrinaline/frontmatter.py, src/adrinaline/model.py, src/adrinaline/git.py, src/adrinaline/data/skills/**, tests/test_guards.py, .github/workflows/release.yml]
amends: [1, 2, 4, 5, 6]
---
# Give ADRs 1, 2, 4, 5 and 6 a scope

## Context and Problem Statement

ADRs 0001 to 0006 were written before `scope` existed, so `adr for` names no decision for most of the codebase, `adr drift` has no baseline for them, and `check --diff` lets commits to their implementing files pass uncited. ADR 0011 closed the same gap for ADRs 3, 8, 9 and 10. ADR 0003 is already covered by 0011 and 0010, and ADR 0007 has a scope.

## Considered Options

- One amending ADR whose own scope lists the files and that says which decision each file carries (this ADR, as 0011)
- One amending ADR per decision
- Edit the `scope` fields in place

## Decision Outcome

Chosen option: one amending ADR, for the reasons given in ADR 0011. Its scope and what each file carries:

| File | Carries |
|---|---|
| `docs/adr/**` | 0001: ADRs are the record; accepted ones are immutable except status and relations |
| `pyproject.toml` | 0002: Python 3.14, argparse, pydantic, ruamel.yaml as the dependencies; 0006: commitizen and hatch-vcs configuration |
| `src/adrinaline/cli.py` | 0002 (argparse); 0005 (`--json`, stable error codes) |
| `src/adrinaline/output.py`, `src/adrinaline/prime.py` | 0005: machine output and the agent briefing |
| `src/adrinaline/data/skills/**` | 0005: the bundled skill |
| `src/adrinaline/frontmatter.py`, `src/adrinaline/model.py` | 0002: ruamel.yaml round-trip and pydantic validation |
| `src/adrinaline/git.py`, `tests/test_guards.py` | 0004: read-only git, guarded by test |
| `.github/workflows/release.yml` | 0006: release from main (also governed by 0007) |

`uv.lock` is left out on purpose: Dependabot commits do not cite ADRs, and a governed lock file would fail `check --diff --strict` on every dependency bump. Dependency choices are visible in `pyproject.toml`.

### Consequences

* Good, because every source module now has at least one governing ADR, so `adr for` is never silent and `adr drift` measures churn on all of them.
* Good, because contributors see a decision to cite on any commit to the CLI, the data model or the release workflow.
* Bad, because `adr for` names this ADR and the reader follows its table to the original decision, as with 0011.
* Bad, because a commit to `cli.py` may need to cite 0011 or this ADR; `ADR: 11, 12` is the usual answer.
