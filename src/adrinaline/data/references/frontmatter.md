# ADR reference

File: `NNNN-slug.md` in the ADR directory. YAML frontmatter, then a body whose first `# ` heading is the title (required). Number and slug live only in the filename.

```yaml
---
status: proposed            # required
date: YYYY-MM-DD            # required, date of the last status change
decision-makers: [Jane Doe] # optional
consulted: []               # optional
informed: []                # optional
tags: [storage]             # optional
scope: ["src/db/**"]        # optional, globs relative to the repository root
supersedes: []              # relations, optional, lists of ADR numbers
superseded-by: []
amends: []
depends-on: []
relates-to: []
---
```

Relation values are integers (`[3, 7]`). Unknown keys are kept. Use hyphenated relation keys, not snake_case.

## Status transitions

Statuses: `proposed`, `accepted`, `rejected`, `deprecated`, `superseded`.

| From | To | Command |
|---|---|---|
| (new) | proposed | `adr new` |
| (new) | accepted | `adr new --accepted` |
| proposed | accepted | `adr accept` |
| proposed | rejected | `adr reject` |
| accepted | deprecated | `adr deprecate` |
| accepted | superseded | `adr supersede OLD --by NEW` |

Anything else fails with `invalid-transition` (`--force` overrides, for repairs only). Each transition sets `date` to today.

## Relations

| Stored | Derived inverse |
|---|---|
| `supersedes` | `superseded-by` (also stored; `adr supersede` writes both sides) |
| `amends` | `amended-by` |
| `depends-on` | `dependency-of` |
| `relates-to` | `relates-to` (symmetric) |

`adr link SRC RELATION DST` adds `RELATION: [DST]` to SRC only (`adr unlink` removes it). RELATION is `amends`, `depends-on` or `relates-to`. `supersedes` may only target an `accepted` ADR. `supersedes` and `depends-on` must not form cycles (`cycle`); an ADR may not relate to itself (`self-relation`).

## JSON (`--json`)

stdout is exactly one JSON document.

- `adr list`: array of ADR objects.
- `adr show REF`: one ADR object plus `"body"`.
- ADR object: `{"number": 7, "id": "0007", "slug": "...", "title": "...", "status": "...", "date": "YYYY-MM-DD", "path": "docs/adr/0007-....md", "tags": [], "scope": [], "relations": {"supersedes": [3]}, "meta": {}}`. `relations` includes derived inverses; `meta` holds other keys.
- `adr check`: `{"ok": bool, "findings": [{"code": "...", "severity": "error|warning", "path": "...", "message": "..."}]}`.
- Errors: `{"error": {"code": "not-found", "message": "...", "details": {}}}`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | `check` found problems (any error; any warning with `--strict`) |
| 2 | Usage error |
| 3 | Domain error: `not-found`, `ambiguous`, `invalid-transition`, `cycle`, `self-relation`, `no-adr-dir`, `exists`, `no-git`, `bad-revision` |

## Check codes

| Code | Severity |
|---|---|
| `bad-filename` | warning |
| `no-frontmatter` | error |
| `missing-field` | error |
| `bad-field` | error |
| `bad-status` | error |
| `bad-date` | error |
| `no-title` | error |
| `duplicate-number` | error |
| `dangling-relation` | error |
| `asymmetric-relation` | error |
| `self-relation` | error |
| `cycle` | error |
| `status-mismatch` | error |
| `number-gap` | warning |
| `no-template` | warning |
| `bad-scope` | error |
| `unknown-relation-key` | warning |
| `scope-matches-nothing` | warning |
| `scoped-change` | warning (only with `--diff REF`) |
