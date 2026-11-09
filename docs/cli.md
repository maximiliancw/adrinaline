# CLI reference

`adr --help` and `adr COMMAND --help` print the same information. The
[specification](SPEC.md) defines the behaviour in detail.

## Global options

`--json`, `--dir` and `-q` work before or after the command name; `--at` only with read commands; `--version` only before it.

| Option | Effect |
|---|---|
| `--json` | print exactly one JSON document on stdout; diagnostics go to stderr |
| `--dir DIR` | use DIR as the ADR directory (skips discovery) |
| `-q`, `--quiet` | no output (except the CI report of `check --format github\|gitlab`) |
| `--at REF` | read ADRs as of a git revision (read commands only) |
| `--version` | print the version |

An ADR `REF` is a number in any padding (`7`, `0007`), a slug (`use-postgresql`), a title (`"Use PostgreSQL"`, slugified before matching) or a substring of the slug; an exact slug wins over substring matches, and a miss suggests close slugs. `--at REF` and `--diff REF` take a git revision.

Human output is coloured on a terminal; it is plain when stdout is not a TTY, when `NO_COLOR` is set, when `TERM` is `dumb`, and always with `--json`.

## Commands

| Command | Options | What it does |
|---|---|---|
| `init` | `--force` overwrites the template and ADR 0001; `--agents` adds the `adr prime` line to `AGENTS.md` and installs the skill into the skill dir of each detected agent (`.claude/skills/adr` for Claude Code, also detected by `~/.claude/CLAUDE.md`, `.agents/skills/adr` for Codex, Cursor and Copilot) without asking | create the ADR directory, template and ADR 0001, print the next steps; on a terminal, offer to wire the coding agent |
| `new [TITLE]` | `--accepted`, `--tag TAG...`, `--scope GLOB...`, `--review-by DATE`, `--body-file PATH` (`-` = stdin), `--edit`, `--supersedes REF...`, `--amends REF...`, `--depends-on REF...`, `--relates-to REF...`, `--force` supersedes ADRs that are not accepted | create a new ADR; on a terminal without TITLE, prompt for title, supersedes and scope |
| `show REF` | `--raw` prints the file verbatim | show one ADR |
| `list` | `--status STATUS...`, `--tag TAG...` | list ADRs |
| `index` | | print a Markdown index table |
| `accept REF` / `reject REF` / `deprecate REF` | `--force` allows any transition | set an ADR's status |
| `review REF` | `--until DATE` also sets `review-by` | record that an ADR was reviewed today (`reviewed: <today>`) |
| `supersede OLD --by NEW` | `--force` supersedes an ADR that is not accepted | mark OLD as superseded by NEW |
| `link REF RELATION REF` / `unlink …` | `RELATION` is `amends`, `depends-on` or `relates-to` | add or remove a relation |
| `graph [REF]` | `--relation R...`, `--depth N` (default: unlimited), `--reverse`, `--format text\|mermaid\|dot\|json`, `--rank` (a usage error with `mermaid` or `dot` unless `--json`) | render the ADR graph |
| `renumber REF --to N` | | give an ADR a new number and update references |
| `log REF` | | show the git history of an ADR |
| `trace REF` | | list the commits whose `ADR:` trailer cites the ADR, newest first |
| `for PATH…` | `--all` includes proposed ADRs | list the ADRs in force that govern each path |
| `drift [REF…]` | | churn per ADR in force with a `scope`: commits and files since its baseline (the later of `date` and `reviewed`), last commit; `--json` for details |
| `check` | `--strict` fails on warnings (never on notes), `--diff REF` reports changed files governed by ADRs and commits that cite none of them, `--format github\|gitlab` prints CI annotations instead of text (a usage error with `--json`; `-q` does not silence it), `--fix` repairs mechanical findings first (ADR 0010; a usage error with `--at`) | validate all ADRs |
| `prime` | `--budget N` limits decisions in force to about N words | print the agent briefing |
| `skill` | `--install DIR` writes the skill and references into DIR | print the bundled agent skill |

Read commands (`--at` allowed): `show`, `list`, `index`, `graph`, `log`,
`trace`, `for`, `drift`, `check`, `prime`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | `check` found problems |
| 2 | usage error |
| 3 | domain error, reported as `{"error": {"code": …}}` with `--json` |

Domain error codes: `not-found`, `ambiguous`, `invalid-transition`, `cycle`,
`self-relation`, `no-adr-dir`, `exists`, `no-git`, `bad-revision`,
`bad-scope`, `bad-config`, `bad-template`, `bad-filename`,
`bad-relation`, `bad-date` (`new --review-by`, `review --until`), `io`, or a check code such as
`no-title` when `new --edit` re-reads the edited file.

## Check codes

Errors: `no-frontmatter`, `missing-field`, `bad-field`, `bad-status`,
`bad-date`, `no-title`, `duplicate-number`, `dangling-relation`,
`asymmetric-relation`, `self-relation`, `cycle`, `status-mismatch`,
`bad-scope`.

Warnings (fail only with `--strict`): `bad-filename`, `number-gap`,
`no-template`, `unknown-relation-key`, `scope-matches-nothing`,
`scoped-change` (only with `--diff`), `uncited-change` (only with `--diff`: a
commit touching governed files cites none of their ADRs), `review-overdue` (an ADR in force has
a `review-by` in the past), `stale-decision` (only when `drift-commits` is
set: at least that many commits touched the ADR's `scope` since its
baseline), `stale-skill` (an installed skill in `.claude/skills/adr`,
`.agents/skills/adr`, `.cursor/skills/adr` or `.github/skills/adr` is from
another `adr` release).

Notes (never fail): `exempt-change` (only with `--diff`: such a commit
carries `ADR-Exempt: reason`).

[SPEC §11](SPEC.md#11-validation-adr-check) gives each code's condition.

## Finding the ADR directory

First match wins:

1. `--dir DIR`.
2. The `ADR_DIR` environment variable.
3. `dir` in `.adrinaline.toml` or in `[tool.adrinaline]` of `pyproject.toml`,
   searched from the current directory up to the git root.
4. A one-line `.adr-dir` file, searched the same way.
5. `docs/adr` at the git root.

The configuration file may also set `template` (default
`<dir>/.template.md`) and `drift-commits` (integer, default `0`; the churn at
which `check` and `prime` report `stale-decision`, `0` = off). Paths are relative to the file that sets them.
