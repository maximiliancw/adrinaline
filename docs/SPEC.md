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
- G9: Decision health is measurable: review dates and churn over an ADR's
  `scope` show which decisions are overdue or stale (`adr drift`,
  `adr review`, `check` warnings), deterministically and from git alone.
- G10: Commits cite the decisions they follow: `ADR:` and `ADR-Exempt:`
  trailers (§13) feed `adr trace` and the `uncited-change` check.

### Non-goals (v1)

- Importing existing ADR sets (adr-tools, Nygard style). `adr check` names, per file, the
  frontmatter that is missing (status and date, read from the adr-tools header where present);
  fixing an import is manual (`check --fix` only repairs mechanical findings, §11).
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
| Black-box tests of the CLI in a subprocess | Go port |
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
  model.py         Adr, Status; pydantic models and transition rules
  frontmatter.py   split/parse/render Markdown + YAML frontmatter (ruamel)
  repo.py          locate ADR dir, load all ADRs, resolve references,
                   allocate numbers, atomic writes, relation updates
  graph.py         AdrGraph: nodes, typed edges, derived inverses,
                   traversal, cycles, rank (PageRank), scope matching,
                   renderers (text, mermaid, dot, json)
  prime.py         briefing: scoring and budgeted selection
  drift.py         decision health: churn per ADR since its baseline, review findings
  check.py         validation rules returning Finding objects
  fix.py           repairs for mechanical findings (`check --fix`)
  git.py           thin wrappers over the `git` executable (read-only)
  output.py        human vs JSON rendering, error envelope, exit codes
  cli.py           argparse wiring; one small function per command
                   (`cmd_<name>`, so `adr for` maps to `cmd_for`; accept,
                   reject and deprecate share `_set_status()`)
  data/            template.md, 0001 ADR text, skills/adr/SKILL.md, references/
tests/
```

`cli.py` keeps the domain rules in `repo`, `check`, `graph` and `fix`: a command
is mostly a call into them plus a call into `output`. It does hold the agent
wiring of §14 (`_skill_dirs`, `_install_skill`, `_installed_skills`) and the
supersede and cycle precheck of `cmd_new`. `repo` loads the files once per command into an
`AdrGraph`; `check`, `prime`, `graph`, `show`, `renumber` and relation
commands all query that graph instead of reading files themselves.

## 4. Storage format

### Directory and filenames

- ADR directory: `docs/adr/` by default (see §5).
- ADR file: `NNNN-slug.md`. `NNNN` is a 4-digit, zero-padded positive integer;
  numbers above 9999 widen naturally (`10000-…`). `slug` is lowercase ASCII,
  words joined by `-`, derived from the title at creation.
- Template: `docs/adr/.template.md` (hidden, so it never appears as an ADR).
- Files in the directory that do not match `^\d{4,}-[a-z0-9]+(-[a-z0-9]+)*\.md$`
  (no leading, trailing or doubled hyphens in the slug) are
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
review-by: YYYY-MM-DD       # optional, when the decision should be revisited
reviewed: YYYY-MM-DD        # optional, date of the last review (`adr review`)
revisit-if: "…"             # optional, the assumption that would invalidate it
supersedes: []              # relations, optional, lists of ADR numbers
superseded-by: []           # the only stored inverse (see §8)
amends: []
depends-on: []
relates-to: []
---
```

- Relation values are integers (`[3, 7]`). Empty relation keys are omitted when
  the tool writes a file.
- `review-by` and `reviewed` are ISO dates (`bad-date` otherwise); `revisit-if`
  is a string (`bad-field` otherwise). All three are absent unless set by hand,
  `adr new --review-by` or `adr review`.
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
`status` and `date` are always set by the tool. `adr new` validates the
rendered ADR before writing it; a template that yields an invalid ADR fails
with `bad-template` and writes nothing.

### Writing files

- Every write goes to a temporary file in the same directory followed by
  `os.replace`, so a crash never leaves a half-written ADR.
- Rewrites change only the keys being edited; ruamel round-trip keeps the rest
  byte-stable where possible.
- New ADR files reserve their number with an exclusive-create (`O_EXCL`)
  marker file first. If the marker already exists and is older than an hour,
  it is treated as abandoned by a crashed or killed process: it is removed
  and its number is reused. If the marker is fresh, a concurrent process is
  assumed to hold the number and the next free number is tried instead. The
  ADR file itself is then written the same way as any other write (temp file
  + `os.replace`), not with `O_EXCL`.
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

The configuration file found in step 2 (`.adrinaline.toml` or
`[tool.adrinaline]`) may also set `template` (path to the template, relative
to that file, default `<dir>/.template.md`) and `drift-commits` (integer,
default `0`: the churn at which `check` reports `stale-decision`, §11; `0`
disables the warning). There is no other configuration. An unreadable or
mistyped configuration fails with `bad-config`.

## 6. ADR references

Wherever a command takes an ADR reference `REF`:

- An integer in any padding (`7`, `07`, `0007`) matches by number.
- Anything else is slugified (§4) and matched against the slugs: an exact
  slug match wins; otherwise every slug containing it matches. So
  `"Use PostgreSQL"`, `use-postgresql` and `postgres` all find
  `0007-use-postgresql.md`.
- Leading/trailing whitespace is stripped.
- Zero matches: error `not-found`; its message names up to three close
  matches (`difflib`, cutoff 0.6) without the `.md` suffix, so a typo is never
  resolved silently, while `details.candidates` lists the same matches as full
  ADR filenames (`NNNN-slug.md`). More than one: error `ambiguous`, naming the
  matching ADRs' filenames (`NNNN-slug.md`), suffix included, in both the
  message and `details.candidates`. A duplicated number is `ambiguous` too.

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
- `adr unlink … relates-to …` removes the edge wherever it is stored (either
  ADR, since `relates-to` is stored once on whichever one declared it); the
  other relations are stored only on the first ADR, so `unlink` touches that
  file alone.
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
  excluded so a replaced ADR does not inherit importance. Hand-rolled.
  High rank means many decisions build on this one ("keystone").
- **Governing ADRs of a path:** ADRs in force whose `scope` contains a glob
  matching the path (`PurePath.full_match`, repository-relative, POSIX
  separators).
- **Drift of an ADR:** its baseline is the later of `date` and `reviewed`; its
  churn is the set of non-merge commits with a committer date after the
  baseline date (a later day, so a review today clears today's commits) that
  touched at least one file matching its `scope` (same matching as above).
  One `git log --since=<earliest baseline> --name-only --no-merges` call over
  the whole repository serves every ADR (`--since` starts a day early to allow
  for committer time zones; `drift.compute` makes the exact comparison); with `--at REF` the log starts at REF
  instead of `HEAD`. ADRs without a `scope` have no drift.

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
| `adr init [--force] [--agents]` | Create the ADR dir, `.template.md` and `0001-record-architecture-decisions.md` (status `accepted`). Idempotent: existing files are left alone unless `--force`. Human output ends with a *Next steps* block (`adr new`, `adr prime`, `adr skill --install DIR` for each detected skill dir (§14) that has no skill); `--json` adds `"next"`. On a terminal (stdin and stdout are TTYs, no `--json`/`-q`) it then offers the agent wiring of §14 as two yes/no prompts; `--agents` performs both without asking. `--json` adds `"agents": {"instructions": path \| null, "skill": [paths]}` when wiring ran. |
| `adr new [TITLE] [--accepted] [--force] [--tag T]... [--scope GLOB]... [--review-by DATE] [--supersedes REF]... [--amends REF]... [--depends-on REF]... [--relates-to REF]... [--body-file PATH\|-] [--edit]` | Allocate the next number (§10), render the template, write the file, apply relations. `--body-file` replaces the template body below the title (`-` reads stdin). `--edit` opens `$VISUAL`/`$EDITOR` afterwards. `--scope` sets a repository-relative glob in the `scope` list; absolute or `..` globs fail with `bad-scope` before any file is written. `--review-by` sets the review date (`bad-date` if not ISO). `--force` lets `--supersedes` target an ADR that is not `accepted`. Prints the new path. Without TITLE on a terminal (and without `--json`/`-q`), prompts for the title (until non-blank), then for `--supersedes` and `--scope` unless given; otherwise a missing TITLE is a usage error. Closed input at any prompt fails with `io`. |
| `adr show REF [--raw]` | Show one ADR: metadata (including the review line: `review-by`, `reviewed`, `revisit-if` when set), resolved relation titles, body. `--raw` prints the file verbatim. |
| `adr list [--status S]... [--tag T]...` | One line per ADR, ordered by number: number, status, date, title. |
| `adr index` | Print a Markdown table (number with link, title, status, date) for pasting into docs. |
| `adr accept REF [--force]`, `adr reject REF [--force]`, `adr deprecate REF [--force]` | Status transitions (§7); `--force` allows any transition. |
| `adr supersede OLD --by NEW [--force]` | Add `NEW supersedes OLD`, mark OLD `superseded`. `--force` allows an OLD that is not `accepted`. |
| `adr link REF RELATION REF` / `adr unlink REF RELATION REF` | Add/remove `amends`, `depends-on` or `relates-to` on the first ADR only; `unlink … relates-to …` removes it wherever it is stored (§8). |
| `adr review REF [--until DATE]` | Record a review: set `reviewed` to today and, with `--until`, `review-by` to DATE (`bad-date` if not ISO). Any status. Prints the ADR by number and title with its review date; `--json` prints the ADR object. |
| `adr drift [REF]...` | Churn per ADR in force that has a `scope` (§8), or only for the given REFs: one line per ADR, highest churn first: number, title, commits and distinct files since the baseline, and the date and subject of the last commit. A closing line counts the ADRs in force without a `scope` (omitted when there are none). `--json` is a list of `{"number", "id", "title", "baseline", "review-by", "revisit-if", "commits", "files": [...], "last": {"commit", "date", "subject"} \| null}`. Fails with `no-git` outside a repository. |
| `adr graph [REF] [--relation R]... [--depth N] [--reverse] [--rank] [--format text\|mermaid\|dot\|json]` | Render the graph: the whole set, or the subgraph reachable from REF (`--reverse` follows inverse edges, by default only `depends-on` and `amends`, giving the impact set). `text` (default) is an indented, deduplicated tree; `mermaid` renders in GitHub/GitLab Markdown; `dot` feeds Graphviz; `json` is `{"nodes": [{"number", "id", "slug", "title", "status", "date", "tags", "path"}], "edges": [{"from", "to", "relation"}]}`. Node styling encodes status in mermaid and dot. `--rank` orders the nodes by rank: text output becomes a flat list, one `rank  NNNN title [status]` line per node, and JSON nodes gain a `rank` value; `--rank` with `mermaid` or `dot` is a usage error unless `--json` is given. |
| `adr check [--strict] [--fix] [--diff REF] [--format text\|github\|gitlab]` | Validate the set (§11). Exit 1 if any error (or any warning with `--strict`); notes never fail. `--diff REF` also reports every changed file (`git diff --name-only $(git merge-base REF HEAD)`, plus untracked files, so commits on REF after the branch point are not counted; exit 3 `bad-revision` when REF shares no history with HEAD) governed by an ADR in force, as `scoped-change` findings naming the ADRs to review (a file whose commits all cite an ADR governing it or are exempt, and that has no uncommitted change, is not reported), and judges every non-merge commit in `REF..HEAD` that touches such a file by its trailers (§13): `uncited-change` or `exempt-change`. CI gate: `adr check --diff origin/main --strict`. `--format` prints CI annotations (see CI annotations). `--fix` repairs mechanical findings first (§11). |
| `adr trace REF` | Commits whose `ADR:` trailer (§13) names REF, newest first: date, short hash, subject. Only non-merge commits reachable from HEAD (with `--at REV`, from REV). No citing commit prints nothing and exits 0. `--json` is a list of `{"commit", "date", "subject", "adrs": [numbers]}`. Fails with `no-git` outside a repository. |
| `adr for PATH... [--all]` | List the ADRs in force that govern each path (§8). `--all` includes `proposed`. |
| `adr renumber REF --to N` | Rename the file, rewrite every relation that points at the old number, and rewrite Markdown links of the form `NNNN-slug.md` in all ADR bodies. Refuses if N is taken. If the old number is duplicated, numeric relations are left alone (they keep pointing at the remaining file) and only filename links are rewritten. |
| `adr log REF` | `git log --follow` for the ADR file (date, short commit hash, author, subject). With `--at REV`, the ADR is looked up at REV and only commits reachable from REV are listed. |
| `adr prime [--budget N]` | Print the agent briefing (§12), optionally limiting the decisions-in-force list to about N words. |
| `adr skill [--install DIR]` | Print the bundled `SKILL.md`. With `--install`, write `SKILL.md` and `references/frontmatter.md` into the skill directory `DIR` (created with parents) and print the written paths. |

Every mutating command prints a short summary of what changed in human mode:
the written paths (`init`, `new`, `unlink`, `renumber`) or the affected ADRs
by number, with titles for `accept`, `reject`, `deprecate`, `supersede` and
`review` (`link` prints numbers only). With `--json` it prints the changed ADRs or
paths as one JSON document.

## 10. Number allocation and collisions

- Next number = 1 + the maximum of (a) numbers in the working tree and (b)
  numbers in the ADR directory on every local branch and remote-tracking ref
  except the current branch (`git for-each-ref refs/heads refs/remotes` +
  `git ls-tree --name-only`, one `ls-tree` per distinct commit so refs
  sharing a commit cost one listing). Numbers used only on other refs are
  reported as a note: "skipped 0007, taken on origin/feature-x".
- No network access: refs are only as fresh as the last fetch.
- Outside git, only (a) applies.
- Collisions that still happen (two branches merged) are found by `adr check`
  (`duplicate-number`) and repaired with `adr renumber`.

## 11. Validation (`adr check`)

Each finding has a stable `code`, a `severity` (`error`, `warning` or
`note`), a `path` (repository-relative, empty for set-wide findings) and a
`message`. Notes inform only: they never affect the exit code, not even with
`--strict`.

| Code | Severity | Condition |
|---|---|---|
| `bad-filename` | warning | File in the ADR dir does not match the naming rule |
| `no-frontmatter` | error | Missing or unparsable YAML frontmatter; for a file with none, the message names the `status` and `date` to add, read from an adr-tools or Nygard header where present |
| `missing-field` | error | `status` or `date` missing |
| `bad-field` | error | A known key has the wrong type (for example a relation that is not a list of numbers) |
| `bad-status` | error | Status not in the allowed set |
| `bad-date` | error | `date`, `review-by` or `reviewed` not an ISO date |
| `no-title` | error | No `# ` heading |
| `duplicate-number` | error | Two files share a number |
| `dangling-relation` | error | Relation points to a non-existent number |
| `asymmetric-relation` | error | `supersedes` and `superseded-by` disagree |
| `self-relation` | error | ADR relates to itself |
| `cycle` | error | Cycle in `supersedes` or `depends-on` |
| `status-mismatch` | error | `superseded-by` set but status ≠ `superseded`, or vice versa |
| `number-gap` | warning | A number between 1 and the maximum is missing and not present on any local branch or remote-tracking ref other than the current one (§10; refs are not consulted with `--at`) |
| `no-template` | warning | `.template.md` missing |
| `bad-scope` | error | `scope` is not a list of relative glob strings |
| `unknown-relation-key` | warning | Frontmatter uses a snake_case key (`superseded_by`, `depends_on`, `relates_to`, `review_by`, `revisit_if`); the hyphenated key is meant |
| `scope-matches-nothing` | warning | A `scope` glob matches no tracked or untracked, non-ignored file (`git ls-files --cached --others --exclude-standard`; with `--at`, the files at that revision) |
| `scoped-change` | warning | With `--diff` only: a changed file is governed by an ADR in force, unless it has no uncommitted change, at least one commit in `REF..HEAD` touched it, and every such commit cites an ADR governing that file or carries `ADR-Exempt:` (§13) |
| `uncited-change` | warning | With `--diff` only: a commit in `REF..HEAD` touches a file governed by an ADR in force, its `ADR:` trailers name none of the ADRs governing the files it touched, and it has no `ADR-Exempt:` trailer. Path is the first governed file; the message names the short hash, subject, governing ADRs and the trailer to add |
| `exempt-change` | note | With `--diff` only: such a commit cites none of its governing ADRs but carries `ADR-Exempt:`; the message names the short hash, subject and reason |
| `review-overdue` | warning | An ADR in force has a `review-by` before today; the message names the date and `adr review N` |
| `stale-decision` | warning | Only when `drift-commits` (§5) is above 0 and there is a git repository: an ADR in force has churn (§8) of at least `drift-commits` commits; the message names the count, the baseline and `adr review N` |
| `stale-skill` | warning | A `SKILL.md` in `.claude/skills/adr`, `.agents/skills/adr`, `.cursor/skills/adr` or `.github/skills/adr` at the git root (or current directory) has no `metadata.version` or one whose release (its leading numeric segments, so `0.3.1.dev16+gabc` counts as `0.3.1`) differs from the running `adr`'s; a `metadata.version` of `"{version}"` (left unfilled by `npx skills add` and the Claude Code plugin, whose own update commands refresh the skill) gives no finding; path is that `SKILL.md`, the message names both versions and `adr skill --install DIR`. No installed skill, no finding |

`adr check --fix` repairs `asymmetric-relation` (writes the missing inverse), `status-mismatch` (sets `superseded` when `superseded-by` is set, keeping `date`), `unknown-relation-key` (renames the key in place unless the hyphenated key exists) and `no-template` (recreates it), then re-checks; the exit code comes from what remains (ADR 0010). Text output prints `fixed <code> <path>: <what>` per repair; `--json` adds a `fixed` list; `--format github|gitlab` print only the report. Not combinable with `--at`.

## 12. Agent interface

### JSON output

- With `--json`, stdout carries exactly one JSON document; nothing else is
  printed to stdout. Diagnostics go to stderr.
- ADR object: `{"number": 7, "id": "0007", "slug": "…", "title": "…",
  "status": "…", "date": "YYYY-MM-DD", "path": "docs/adr/0007-….md",
  "tags": [], "scope": [], "review-by": "YYYY-MM-DD" | null, "reviewed": "YYYY-MM-DD" | null,
  "revisit-if": "…" | null, "relations": {"supersedes": [3], …}, "meta": {…other keys}}`.
  `show` adds `"body"`, and `"successor"` (number at the end of the
  `superseded-by` chain) when the ADR is superseded. `new` adds `"skipped"`
  (`{"0003": "origin/main"}`: numbers taken on other refs, §10; `{}` if none).
- Lists are JSON arrays. `check` returns `{"ok": bool, "findings": […]}`.
- `prime` returns `{"dir", "counts" (ADRs per status present), "in_force" (ADR
  objects shown), "omitted" (in-force ADRs left out by `--budget`),
  "needs_review" (findings), "proposed" (ADR objects), "rules" (the rules text
  of the briefing's last section)}`.
- Errors: `{"error": {"code": "not-found", "message": "…", "details": {…}}}`.

### Human output

Human output (without `--json`) uses ANSI colour for statuses, `check`
severities (including `note`) and its `ok`, and `drift` ids when stdout is a terminal, `NO_COLOR` is unset and
`TERM` is not `dumb`. Piped output, `--json`, `prime` and `index` never contain
escape codes.

### CI annotations

`adr check --format github|gitlab` prints the findings for a CI system
instead of the human text; the exit code is unchanged, `-q` does not silence
it, and combining it with `--json` is a usage error.

- `github`: one GitHub Actions workflow command per finding,
  `::LEVEL file=PATH,line=1,title=CODE::MESSAGE`, where LEVEL is `error`,
  `warning` or `notice` (for a note). Set-wide findings omit `file` and
  `line`. Values use the workflow-command escaping. A clean run prints nothing.
- `gitlab`: a GitLab Code Quality report, a JSON array (`[]` when clean) of
  `{"description", "check_name", "fingerprint", "severity", "location":
  {"path", "lines": {"begin": 1}}}`. `check_name` is the code; severity is
  `major` for errors, `minor` for warnings and `info` for notes; the
  fingerprint hashes code, path and the finding's index among those with the
  same code and path, so it survives message changes such as a new commit
  hash; set-wide findings use the ADR directory as path.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | `check` found problems |
| 2 | Usage error (argparse) |
| 3 | Domain error, reported as an error envelope (`not-found`, `ambiguous`, `invalid-transition`, `cycle`, `self-relation`, `no-adr-dir`, `exists`, `no-git`, `bad-revision`, `bad-scope`, `bad-config`, `bad-template`, `bad-filename`, `bad-relation`, `io`, or a §11 parse code such as `no-title` when `new --edit` re-reads the edited file) |

### `adr prime`

Prints a compact briefing in Markdown (JSON with `--json`):

1. Where the ADRs live and how many exist per status.
2. A one-line-per-ADR list of the ADRs in force (§8; number, title, tags),
   with their `depends-on`/`amends` edges inline.
3. Needs review: one line per ADR in force that is `review-overdue` or
   `stale-decision` (§11; the same conditions and config as `check`), naming
   the reason and `adr review N`. Omitted when empty.
4. Open `proposed` ADRs.
5. A command cheat sheet and the rules: when to write an ADR, never edit an
   accepted ADR's decision (supersede or amend instead), run `adr review N`
   after revisiting a decision, cite the ADRs a commit follows with an
   `ADR: N` trailer (or `ADR-Exempt: reason`), run `adr check` before
   finishing.

With `--budget N`, sections 1, 3, 4 and 5 are always printed in full; section 2
is limited to about N words and filled with ADRs in force in descending
score. The top-scored ADR is always shown, even if its line alone exceeds N:

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

`data/skills/adr/SKILL.md` follows the Agent Skills format (name, description,
instructions). It tells agents when a decision deserves an ADR, how to write
one with `adr new --body-file -`, how to supersede or amend, and how to record
a review with `adr review`, and how to cite ADRs in commit trailers.
`adr skill` prints it.

## 13. Git integration (read-only)

Git is invoked as a subprocess; if `git` is missing or the directory is not a
repository, git features degrade silently (no root detection beyond §5, no
cross-branch allocation, `adr log` fails with `no-git`).

Used for: repository root (`git rev-parse --show-toplevel`), default
`decision-makers` entry on `init` (`git config user.name`, omitted if unset),
cross-branch numbers (§10), `adr log`, drift (§8: `adr drift`,
`stale-decision`, `adr prime`), commit trailers (`adr trace`,
`uncited-change`). Never: `add`, `commit`, `fetch`, `checkout`,
or any other command that writes.

### Commit trailers

A commit cites ADRs with one or more `ADR:` trailers, each holding ADR
numbers separated by commas or spaces (`ADR: 7`, `ADR: 0007, 0012`); tokens
that are not numbers are ignored. `ADR-Exempt: reason` declares a governed
change that follows no ADR. Trailers are read with git's own parser
(`git log --format=%(trailers:key=ADR,valueonly)`), so they must sit in the
final paragraph of the message as git defines it. A number that names no ADR
cites nothing.

## 14. `adr init` content

- `.template.md`: the template from §4.
- `0001-record-architecture-decisions.md`: status `accepted`, MADR 4 body
  stating that the project records architecturally significant decisions as
  ADRs in this directory, in MADR 4 format with YAML frontmatter, managed with
  `adr`; that accepted ADRs are immutable except for status and relations;
  and that changes happen by superseding or amending.
- Agent wiring (prompted on a terminal, or `--agents`): append the line
  ``Run `adr prime` at the start of every session and follow the ADRs it lists.``
  to `AGENTS.md` at the git root (or current directory), or to `CLAUDE.md` when
  only that file exists; create `AGENTS.md` when neither exists; skip when the
  file already mentions `adr prime`. Then install the skill (§12) into the
  skill dir of each agent detected at that root: `.claude/skills/adr` when
  `CLAUDE.md` or `.claude/` exists, or the user-wide `~/.claude/CLAUDE.md`; `.agents/skills/adr` (read by Codex,
  Cursor and Copilot) when `AGENTS.md`, `.agents/`, `.cursor/` or `.github/`
  exists, or when nothing is detected. Each dir is written at most once.
  Both steps are idempotent.

## 15. Testing and quality

- `pytest`. Unit tests for `frontmatter`, `model`, `repo`, `check`.
- CLI tests run the CLI as a subprocess (`python -m adrinaline`, the same entry
  point as `adr`) inside temporary git repositories created per test,
  covering each command in human and `--json` mode, including error codes.
- `ruff check`, `ruff format --check`, `ty check` must pass.
- CI (GitHub Actions): on pull requests, the commit-message, lint, type and
  `adr check --strict` gates and a strict docs build run on `ubuntu-latest`;
  tests run on `ubuntu-latest` and `macos-latest` with Python 3.14. Every push
  to `main` releases when commitizen finds a bump: `uv build`, maintainer
  approval in the `release` environment (ADR 0007), tag, PyPI trusted
  publishing, GitHub Release (ADR 0006). Docs are built with zensical and
  published to GitHub Pages.

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
    `adr new "X" --scope "src/db/**"` then `adr accept` makes
    `adr for src/db/conn.py` list it; an absolute or `..` glob exits with
    `bad-scope` and writes no file.
20. After modifying a governed file, `adr check --diff HEAD` reports
    `scoped-change` naming the governing ADR and exits 0; with `--strict` it
    exits 1.
21. After superseding 0002 in a new commit, `adr list --at HEAD~1` shows 0002
    as `accepted`, and `adr accept 3 --at HEAD~1` exits 2.
22. On a fixture where 0002 is the target of three `depends-on` edges,
    `adr graph --rank --json` ranks 0002 first; ranks sum to 1 within 1e-6.
23. `adr prime --budget 150` on a 30-ADR fixture prints at most 150 words of
    ADR entries (unless the top-scored entry alone is longer), always includes
    the top-scored ADR, and ends with the left-out count.
24. `adr review 2 --until 2099-01-01` writes `reviewed: <today>` and
    `review-by: 2099-01-01` to 0002 and changes nothing else; `adr review 2
    --until 2099-13-01` exits 3 with `bad-date` and writes nothing;
    `adr new "X" --review-by 2099-01-01` writes `review-by`.
25. An ADR in force with `review-by` in the past makes `adr check` report
    `review-overdue` and exit 0 (1 with `--strict`); a `proposed` or
    `superseded` ADR with the same date does not.
26. On a fixture where 0002 has `scope: ["src/db/**"]`, two commits after its
    `date` touch `src/db/` and one touches `src/other/`, `adr drift --json`
    reports `commits: 2` for 0002 with both files; after `adr review 2` and a
    commit, `adr drift` reports 0; `adr drift --at HEAD~1` reports the earlier
    state; an ADR without `scope` is not listed and is counted in the closing
    line.
27. With `drift-commits = 2` in `.adrinaline.toml`, the fixture of 26 makes
    `adr check` report `stale-decision` for 0002 naming the count; without the
    key, and with `drift-commits = 3`, it does not.
28. `adr prime` on the fixtures of 25 and 27 prints a "Needs review" section
    naming both ADRs and their repair command; without them the section is
    absent and `--budget` output is unchanged.
29. `adr init --agents` in a fresh repo appends the `adr prime` line to
    `AGENTS.md` (to `CLAUDE.md` when only that exists) and writes
    `.agents/skills/adr/SKILL.md` (`.claude/skills/adr/SKILL.md` when only
    `CLAUDE.md` exists; both when `.claude/` exists too); a second run leaves `AGENTS.md`
    byte-identical. Plain `adr init` off a terminal writes nothing outside the
    ADR directory and prints a *Next steps* block. On a terminal, `adr init`
    asks before each wiring step and `adr new` without TITLE prompts for the
    title, supersedes and scope.
30. `adr show "Use PostgreSQL"` and `adr show use-postgresql` resolve
    `0002-use-postgresql.md` even when `0003-use-postgresql-17.md` exists;
    `adr show use-postgrs` fails with `not-found` naming `0002-use-postgresql`
    as a candidate.
31. On a fixture with commits citing `ADR: 2`, `ADR: 0002, 0003`, `ADR: 3`
    and none, `adr trace 2 --json` lists exactly the first two, newest
    first; `adr trace 2 --at HEAD~3` lists only the first.
32. With 0002 in force and `scope: ["src/db/**"]`, a commit after REF that
    touches `src/db/x.py` makes `adr check --diff REF` report
    `uncited-change` without a trailer and with `ADR: 3` (an ADR not
    governing it), and with `ADR: 2` neither `uncited-change` nor
    `scoped-change`, so `adr check --diff REF --strict` exits 0; an
    uncommitted edit to `src/db/x.py` brings `scoped-change` back.
33. The same commit with `ADR-Exempt: generated code` is reported as
    `exempt-change` with severity `note`, and `adr check --diff REF --strict`
    exits 0.
34. Each code `adr check --fix` repairs is fixed on its fixture and
    re-checks clean; a second run fixes nothing; status `superseded` without
    `superseded-by` and a snake_case key next to its hyphenated twin are left
    byte-identical.
