# adrinaline: specification

`adrinaline` ("ADRs in a line") manages Architecture Decision Records the way
[`ticket`](https://github.com/wedow/ticket) manages tickets: plain Markdown files
in the repository, a fast CLI named `adr`, and output that humans and coding
agents both read reliably.

## 1. Goals and non-goals

### Goals

- G1: One command bootstraps an ADR practice in any repository (`adr init`).
- G2: Every ADR is a plain Markdown file with YAML frontmatter; hand edits are
  first-class and the tool never becomes the only way to change a record.
- G3: ADRs are numbered sequentially (`0001`, `0002`, …). Collisions between
  branches are detected early and repaired with one command.
- G4: The CLI is the agent interface ("bash is all you need"): every command
  supports `--json`, errors are machine-readable, and `adr prime` gives an agent
  everything it needs at session start.
- G5: `adr check` validates the whole ADR set and is suitable for CI and
  pre-commit.
- G6: Git-aware but read-only: the tool never stages, commits or fetches.
- G7: The ADR set is a typed graph. One in-memory graph backs every query,
  validation and export, and `adr graph` renders it as text, Mermaid, DOT or
  JSON.
- G8: ADRs connect to code and history: `scope` globs tie decisions to files
  (`adr for`, `adr check --diff`), and every read command works against any
  git revision (`--at REF`).

### Non-goals (v1)

- Importing existing ADR sets (adr-tools, Nygard style). `adr check` reports
  what does not conform; fixing is manual.
- TOML frontmatter.
- A plugin system, an MCP server, a web UI or a static-site generator.
- An interactive graph viewer. Planned for v2 as `adr graph --format html`
  (one self-contained page built on the JSON export).
- A generated index file on disk (`adr index` prints to stdout only).
- Standalone binaries. Distribution is PyPI only.

## 2. Prior art and reuse decision

Both `wedow/ticket` (bash, MIT) and its Go port `radutopala/ticket` (MIT) were
reviewed. Neither is forked: their ID model (random) differs from ADR
numbering (sequential), most of their features (priorities, claims, bulk,
stats) do not apply, and the bash original parses YAML with sed/awk, which is
fragile. No code is copied. Ideas adopted:

| Idea | Source |
|---|---|
| Short agent hint plus a comprehensive `help` | ticket |
| Partial ID resolution, whitespace-tolerant | ticket |
| Directory discovery by walking up, env override | ticket |
| Typed relations with tree view and cycle checks | ticket |
| Global `--json` flag through one output helper | Go port |
| Library core with a thin CLI layer | Go port |
| Black-box tests against the installed command | Go port |
| Shipped agent skill (`SKILL.md`) | Go port |
| `.adr-dir` file for locating the ADR directory | adr-tools |

## 3. Stack and packaging

- Python 3.14+, managed with `uv`. Relied on: `PurePath.full_match` for `**`
  glob matching (3.13+) without a dependency.
- Runtime dependencies: `pydantic` (ADR model and validation), `ruamel.yaml`
  (round-trip YAML that preserves comments, key order and quoting on rewrite).
  CLI parsing uses stdlib `argparse`.
- Dev tooling: `pytest`, `ruff`, `ty`.
- PyPI distribution `adrinaline`, console scripts `adr` and `adrinaline`
  (identical). Install via `uv tool install adrinaline` or run via
  `uvx adrinaline`.

### Package layout

```
src/adrinaline/
  __init__.py      version
  model.py         Adr, Status, Relation; pydantic models and transition rules
  frontmatter.py   split/parse/render Markdown + YAML frontmatter (ruamel)
  repo.py          locate ADR dir, load all ADRs, resolve references,
                   allocate numbers, atomic writes, relation updates
  graph.py         AdrGraph: nodes, typed edges, derived inverses,
                   traversal, cycles, rank (PageRank), scope matching,
                   renderers (text, mermaid, dot, json)
  prime.py         briefing: scoring and budgeted selection
  check.py         validation rules returning Finding objects
  git.py           thin wrappers over the `git` executable (read-only)
  output.py        human vs JSON rendering, error envelope, exit codes
  cli.py           argparse wiring; one small function per command
                   (`cmd_<name>`, so `adr for` maps to `cmd_for`)
  data/            template.md, 0001 ADR text, SKILL.md, prime text
tests/
```

`cli.py` holds no domain logic; every command is a call into `repo`/`check`
plus a call into `output`. `repo` loads the files once per command into an
`AdrGraph`; `check`, `prime`, `graph`, `show`, `renumber` and relation
commands all query that graph instead of reading files themselves.

## 4. Storage format

### Directory and filenames

- ADR directory: `docs/adr/` by default (see §5).
- ADR file: `NNNN-slug.md`. `NNNN` is a 4-digit, zero-padded positive integer;
  numbers above 9999 widen naturally (`10000-…`). `slug` is lowercase ASCII,
  words joined by `-`, derived from the title at creation.
- Template: `docs/adr/.template.md` (hidden, so it never appears as an ADR).
- Files in the directory that do not match `^\d{4,}-[a-z0-9-]+\.md$` are
  ignored by all commands except `check`, which reports them as warnings
  (`README.md` and dotfiles are exempt).
- Number and slug live only in the filename; they are never duplicated in
  frontmatter.

### Frontmatter

YAML between `---` lines at the top of the file. Keys follow MADR 4 where MADR
defines them.

```yaml
---
status: proposed            # required
date: YYYY-MM-DD            # required, date of the last status change
decision-makers: [Jane Doe] # MADR, optional
consulted: []               # MADR, optional
informed: []                # MADR, optional
tags: [storage]             # optional
scope: ["src/db/**"]        # optional, globs relative to the repository root
supersedes: []              # relations, optional, lists of ADR numbers
superseded-by: []           # the only stored inverse (see §8)
amends: []
depends-on: []
relates-to: []
---
```

- Relation values are integers (`[3, 7]`). Empty relation keys are omitted when
  the tool writes a file.
- Unknown keys are preserved on rewrite and ignored otherwise.
- The title is the first `# ` heading of the body. It is required.

### Body

New ADRs are rendered from the template (MADR 4 minimal):

```markdown
# {title}

## Context and Problem Statement

## Considered Options

## Decision Outcome

Chosen option: "…", because …

### Consequences

* Good, because …
* Bad, because …
```

`{title}` is the only placeholder. A project may edit `.template.md` freely,
including its frontmatter defaults (for example `tags` or `decision-makers`);
`status` and `date` are always set by the tool.

### Writing files

- Every write goes to a temporary file in the same directory followed by
  `os.replace`, so a crash never leaves a half-written ADR.
- Rewrites change only the keys being edited; ruamel round-trip keeps the rest
  byte-stable where possible.
- New ADR files are created with exclusive create (`O_EXCL`); if the number is
  taken by a concurrent process, the next free number is tried.
- Block-style YAML lists are re-indented (and flow lists kept) on rewrite; this
  formatting change is accepted.

## 5. Locating the ADR directory

First match wins:

1. `ADR_DIR` environment variable (absolute, or relative to the current
   directory).
2. `dir` in `[tool.adrinaline]` of the nearest `pyproject.toml`, or in
   `.adrinaline.toml` (top-level key `dir`), searching from the current
   directory up to the git root. Relative to the file that defines it. If
   both files exist in the same directory, `.adrinaline.toml` wins.
3. An `.adr-dir` file (adr-tools convention), searched the same way; its single
   line is a path relative to the directory containing it.
4. `docs/adr` relative to the git root, if it exists.

Outside a git repository, steps 2–3 search up to the filesystem root and step 4
uses the current directory. If nothing exists, every command except `init`
fails with error code `no-adr-dir`. `adr init` creates the directory resolved
by steps 1–3, else `<git root or cwd>/docs/adr`.

`.adrinaline.toml` may also set `template` (path to the template, default
`<dir>/.template.md`). There is no other configuration.

## 6. ADR references

Wherever a command takes an ADR reference `REF`:

- An integer in any padding (`7`, `07`, `0007`) matches by number.
- Anything else matches as a case-insensitive substring of the slug.
- Leading/trailing whitespace is stripped.
- Zero matches: error `not-found`. More than one: error `ambiguous`, listing
  candidates. A duplicated number is `ambiguous` too.

## 7. Status lifecycle

Statuses: `proposed`, `accepted`, `rejected`, `deprecated`, `superseded`.

| From | To | Command |
|---|---|---|
| (new) | proposed | `adr new` |
| (new) | accepted | `adr new --accepted` |
| proposed | accepted | `adr accept` |
| proposed | rejected | `adr reject` |
| accepted | deprecated | `adr deprecate` |
| accepted | superseded | `adr supersede` |

Any other transition fails with `invalid-transition`. `--force` permits it and
is meant for repairs. Each transition sets `date` to today (local date,
ISO 8601).

## 8. Relations

| Relation (stored) | Inverse (derived) | Kind | Status effect |
|---|---|---|---|
| `supersedes` | `superseded-by` (also stored) | directional | target becomes `superseded` |
| `amends` | `amended-by` | directional | none |
| `depends-on` | `dependency-of` | directional | none |
| `relates-to` | `relates-to` | symmetric | none |

- Only forward relations are stored, on the ADR that declares them.
  `relates-to` is stored once, on the ADR where it was added.
- Exception: `superseded-by` is also stored on the superseded ADR, so a reader
  of that file alone sees what replaced it. `adr supersede` writes both sides.
- All inverses are derived by the graph and appear in `show`, `graph` and
  JSON output as if stored.
- `supersedes` may only target an `accepted` ADR (`--force` overrides).
- Old ADRs are never touched when a new ADR amends, depends on or relates to
  them, which keeps merge conflicts on old files rare.
- An ADR may not relate to itself. `supersedes` and `depends-on` must not
  form cycles; commands refuse to create one (`cycle`), and `check` reports
  cycles introduced by hand edits.

### Graph model

`AdrGraph` holds one node per ADR (number, slug, title, status, date, tags,
path) and one typed, directed edge per stored relation (`relates-to` edges
are treated as undirected in queries). Plain dicts; cycle detection uses
stdlib `graphlib`. Derived views:

- **In force:** `accepted` ADRs with no `superseded-by`.
- **Current successor:** follow `superseded-by` to the end of the chain.
- **Impact of REF:** ADRs that reach REF through `depends-on` or `amends`
  (who is affected if REF changes).
- **Rank:** PageRank over the graph (damping 0.85, power iteration until the
  change is below 1e-9 or 100 iterations). Edges `depends-on` and `amends`
  pass weight to their target, `relates-to` both ways; `supersedes` is
  excluded so a replaced ADR does not inherit importance. Hand-rolled, about
  15 lines. High rank means many decisions build on this one ("keystone").
- **Governing ADRs of a path:** ADRs in force whose `scope` contains a glob
  matching the path (`PurePath.full_match`, repository-relative, POSIX
  separators).

### Revisions (`--at REF`)

Every read command accepts the global flag `--at REF` (any git revision:
commit, tag, branch). The ADR set is then loaded from git instead of the
working tree: `git ls-tree` lists the ADR directory at REF and one
`git cat-file --batch` process reads all files. The ADR directory is resolved
in the working tree (§5) and looked up at the same path in REF. Mutating
commands reject `--at` with a usage error. Typical use: "which decisions were
in force at release v1.2" (`adr list --at v1.2 --status accepted`).

## 9. Commands

Global flags: `--json` (machine output), `--dir PATH` (overrides §5),
`--at REF` (read commands only, §8),
`-q/--quiet` (no human output on success), `--version`, `-h/--help`.

| Command | Effect |
|---|---|
| `adr init [--force]` | Create the ADR dir, `.template.md` and `0001-record-architecture-decisions.md` (status `accepted`). Idempotent: existing files are left alone unless `--force`. |
| `adr new TITLE [--accepted] [--tag T]... [--supersedes REF]... [--amends REF]... [--depends-on REF]... [--relates-to REF]... [--body-file PATH\|-] [--edit]` | Allocate the next number (§10), render the template, write the file, apply relations. `--body-file` replaces the template body below the title (`-` reads stdin). `--edit` opens `$VISUAL`/`$EDITOR` afterwards. Prints the new path. |
| `adr show REF [--raw]` | Show one ADR: metadata, resolved relation titles, body. `--raw` prints the file verbatim. |
| `adr list [--status S]... [--tag T]...` | One line per ADR, ordered by number: number, status, date, title. |
| `adr index` | Print a Markdown table (number with link, title, status, date) for pasting into docs. |
| `adr accept REF`, `adr reject REF`, `adr deprecate REF` | Status transitions (§7). |
| `adr supersede OLD --by NEW` | Add `NEW supersedes OLD`, mark OLD `superseded`. |
| `adr link REF RELATION REF` / `adr unlink REF RELATION REF` | Add/remove `amends`, `depends-on` or `relates-to` on the first ADR only (§8). |
| `adr graph [REF] [--relation R]... [--depth N] [--reverse] [--rank] [--format text\|mermaid\|dot\|json]` | Render the graph: the whole set, or the subgraph reachable from REF (`--reverse` follows inverse edges, by default only `depends-on` and `amends`, giving the impact set). `text` (default) is an indented, deduplicated tree; `mermaid` renders in GitHub/GitLab Markdown; `dot` feeds Graphviz; `json` is `{"nodes": […], "edges": [{"from", "to", "relation"}]}`. Node styling encodes status in mermaid and dot. `--rank` orders output by rank and adds a `rank` value to text and JSON nodes. |
| `adr check [--strict] [--diff REF]` | Validate the set (§11). Exit 1 if any error (or any warning with `--strict`). `--diff REF` also reports every changed file (`git diff --name-only REF`, plus untracked files) governed by an ADR in force, as `scoped-change` findings naming the ADRs to review. CI gate: `adr check --diff origin/main --strict`. |
| `adr for PATH... [--all]` | List the ADRs in force that govern each path (§8). `--all` includes `proposed`. |
| `adr renumber REF --to N` | Rename the file, rewrite every relation that points at the old number, and rewrite Markdown links of the form `NNNN-slug.md` in all ADR bodies. Refuses if N is taken. If the old number is duplicated, numeric relations are left alone (they keep pointing at the remaining file) and only filename links are rewritten. |
| `adr log REF` | `git log --follow` for the ADR file (date, author, subject). |
| `adr prime [--budget N]` | Print the agent briefing (§12), optionally limited to about N words. |
| `adr skill` | Print the bundled `SKILL.md` so it can be redirected into an agent's skill directory. |

All mutating commands print what changed (paths and fields) in human mode, and
the same as JSON with `--json`.

## 10. Number allocation and collisions

- Next number = 1 + the maximum of (a) numbers in the working tree and (b)
  numbers in the ADR directory on every local branch and remote-tracking ref
  (`git for-each-ref refs/heads refs/remotes` + `git ls-tree --name-only`).
  Numbers used only on other refs are reported as a note: "skipped 0007,
  taken on origin/feature-x".
- No network access: refs are only as fresh as the last fetch.
- Outside git, only (a) applies.
- Collisions that still happen (two branches merged) are found by `adr check`
  (`duplicate-number`) and repaired with `adr renumber`.

## 11. Validation (`adr check`)

Each finding has a stable code, a severity, a file and a message.

| Code | Severity | Condition |
|---|---|---|
| `bad-filename` | warning | File in the ADR dir does not match the naming rule |
| `no-frontmatter` | error | Missing or unparsable YAML frontmatter |
| `missing-field` | error | `status` or `date` missing |
| `bad-field` | error | A known key has the wrong type (for example a relation that is not a list of numbers) |
| `bad-status` | error | Status not in the allowed set |
| `bad-date` | error | `date` not an ISO date |
| `no-title` | error | No `# ` heading |
| `duplicate-number` | error | Two files share a number |
| `dangling-relation` | error | Relation points to a non-existent number |
| `asymmetric-relation` | error | `supersedes` and `superseded-by` disagree |
| `self-relation` | error | ADR relates to itself |
| `cycle` | error | Cycle in `supersedes` or `depends-on` |
| `status-mismatch` | error | `superseded-by` set but status ≠ `superseded`, or vice versa |
| `number-gap` | warning | A number between 1 and the maximum is missing |
| `no-template` | warning | `.template.md` missing |
| `bad-scope` | error | `scope` is not a list of relative glob strings |
| `unknown-relation-key` | warning | Frontmatter uses a snake_case relation key (`superseded_by`, `depends_on`, `relates_to`, `amended_by`, `dependency_of`); the hyphenated key is meant |
| `scope-matches-nothing` | warning | A `scope` glob matches no file in `git ls-files` |
| `scoped-change` | warning | With `--diff` only: a changed file is governed by an ADR in force |

`adr check --fix` is not in v1.

## 12. Agent interface

### JSON output

- With `--json`, stdout carries exactly one JSON document; nothing else is
  printed to stdout. Diagnostics go to stderr.
- ADR object: `{"number": 7, "id": "0007", "slug": "…", "title": "…",
  "status": "…", "date": "YYYY-MM-DD", "path": "docs/adr/0007-….md",
  "tags": [], "scope": [], "relations": {"supersedes": [3], …}, "meta": {…other keys}}`.
  `show` adds `"body"`.
- Lists are JSON arrays. `check` returns `{"ok": bool, "findings": […]}`.
- Errors: `{"error": {"code": "not-found", "message": "…", "details": {…}}}`.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | `check` found problems |
| 2 | Usage error (argparse) |
| 3 | Domain error (`not-found`, `ambiguous`, `invalid-transition`, `cycle`, `self-relation`, `no-adr-dir`, `exists`, `no-git`, `bad-revision`) |

### `adr prime`

Prints a compact briefing in Markdown (JSON with `--json`):

1. Where the ADRs live and how many exist per status.
2. A one-line-per-ADR list of the ADRs in force (§8; number, title, tags),
   with their `depends-on`/`amends` edges inline.
3. Open `proposed` ADRs.
4. A command cheat sheet and the rules: when to write an ADR, never edit an
   accepted ADR's decision (supersede or amend instead), run `adr check` before
   finishing.

With `--budget N`, sections 1, 3 and 4 are always printed in full; section 2
is limited to about N words and filled with ADRs in force in descending
score:

    score = 0.5 · rank (normalised to 0–1)
          + 0.3 · scope hit (1 if the ADR governs a file changed in the working
                  tree, from `git status --porcelain`, else 0)
          + 0.2 · recency (1 for the newest `date`, 0 for the oldest, linear)

Candidates are popped from a `heapq` heap ordered by (score, number); each
ADR is added if its line still fits (smaller ones may fill remaining space),
and a closing line names how many were left out and how to get them
(`adr list --status accepted`). Weights are constants, not configuration.

Intended use: a single line in `AGENTS.md`/`CLAUDE.md` ("Run `adr prime` at
session start") or a session-start hook.

### Skill

`data/SKILL.md` follows the Agent Skills format (name, description,
instructions). It tells agents when a decision deserves an ADR, how to write
one with `adr new --body-file -`, and how to supersede or amend. `adr skill`
prints it.

## 13. Git integration (read-only)

Git is invoked as a subprocess; if `git` is missing or the directory is not a
repository, git features degrade silently (no root detection beyond §5, no
cross-branch allocation, `adr log` fails with `no-git`).

Used for: repository root (`git rev-parse --show-toplevel`), default
`decision-makers` entry on `init` (`git config user.name`, omitted if unset),
cross-branch numbers (§10), `adr log`. Never: `add`, `commit`, `fetch`,
`checkout`, or any other command that writes.

## 14. `adr init` content

- `.template.md`: the template from §4.
- `0001-record-architecture-decisions.md`: status `accepted`, MADR 4 body
  stating that the project records architecturally significant decisions as
  ADRs in this directory, in MADR 4 format with YAML frontmatter, managed with
  `adr`; that accepted ADRs are immutable except for status and relations;
  and that changes happen by superseding or amending.

## 15. Testing and quality

- `pytest`. Unit tests for `frontmatter`, `model`, `repo`, `check`.
- CLI tests run `adr` as a subprocess inside temporary git repositories created
  per test, covering each command in human and `--json` mode, including error
  codes.
- `ruff check`, `ruff format --check`, `ty check` must pass.
- CI (GitHub Actions): lint and tests on `ubuntu-latest` and `macos-latest`
  with Python 3.14. A pushed tag `v*` builds with
  `uv build` and publishes to PyPI via trusted publishing.

## 16. Acceptance criteria

Each criterion is an automated test.

1. In an empty git repo, `adr init` creates `docs/adr/.template.md` and
   `docs/adr/0001-record-architecture-decisions.md`; `adr check` exits 0.
2. Running `adr init` twice changes nothing.
3. `adr new "Use PostgreSQL"` creates `docs/adr/0002-use-postgresql.md` with
   `status: proposed`, today's date and title heading; run from a subdirectory
   it writes to the same directory.
4. `ADR_DIR`, `.adrinaline.toml`, `[tool.adrinaline]` and `.adr-dir` each
   redirect the directory, in the precedence of §5.
5. With a branch `other` holding `0003-x.md`, `adr new` on `main` (which ends
   at 0002) creates `0004-…` and reports the skip.
6. `adr show 2`, `adr show 0002` and `adr show postgres` print the same ADR;
   `adr show zzz` exits 3 with code `not-found`.
7. `adr accept 2` succeeds; a second `adr accept 2` exits 3 with
   `invalid-transition`.
8. `adr supersede 2 --by 3` writes `supersedes: [2]` to 0003,
   `superseded-by: [3]` and `status: superseded` to 0002.
9. `adr link 3 depends-on 2` followed by `adr link 2 depends-on 3` exits 3
   with `cycle`.
10. Each `check` code in §11 is triggered by a fixture and reported with its
    code; `--json` output validates against the documented shape.
11. Duplicate 0004 files: `adr check` exits 1 with `duplicate-number`;
    `adr renumber <slug> --to 5` fixes it, rewrites relations and body links,
    and `adr check` exits 0.
12. Every command with `--json` emits a single parsable JSON document on
    stdout, both on success and on domain errors.
13. A hand-added YAML comment and an unknown key survive `adr accept`.
14. `adr prime` lists exactly the ADRs in force and the proposed ones.
15. No test observes a git write: `git status --porcelain` shows only ADR file
    changes and `git log` is unchanged after every command.
16. `adr link 3 amends 2` changes only 0003; `adr show 2 --json` lists 3
    under `amended-by`.
17. `adr graph --format json` returns every ADR as a node and every stored
    relation as an edge; `--format mermaid` and `--format dot` output parse
    (mermaid and dot compared against snapshot files; dot additionally
    through `dot -Tsvg` when Graphviz is installed, skipped otherwise).
18. `adr graph 2 --reverse` lists exactly the ADRs that depend on or amend
    0002, directly or transitively.
19. `adr for src/db/conn.py` lists exactly the ADRs in force whose `scope`
    matches it; a superseded ADR with the same scope is not listed.
20. After modifying a governed file, `adr check --diff HEAD` reports
    `scoped-change` naming the governing ADR and exits 0; with `--strict` it
    exits 1.
21. After superseding 0002 in a new commit, `adr list --at HEAD~1` shows 0002
    as `accepted`, and `adr accept 3 --at HEAD~1` exits 2.
22. On a fixture where 0002 is the target of three `depends-on` edges,
    `adr graph --rank --json` ranks 0002 first; ranks sum to 1 within 1e-6.
23. `adr prime --budget 150` on a 30-ADR fixture prints at most 150 words of
    ADR entries, always includes the top-scored ADR, and ends with the
    left-out count.
