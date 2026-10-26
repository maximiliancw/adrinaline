# adrinaline

ADRs in a line: git-native Architecture Decision Records for humans and coding agents.

`adr` keeps decisions as Markdown files with YAML frontmatter in your repository, numbers them sequentially, links them into a graph, ties them to the code they govern, and answers every question in plain text or JSON.

## Install

```bash
uv tool install adrinaline   # provides `adr` (and `adrinaline`)
# or run without installing:
uvx adrinaline --help
```

Requires Python 3.14+ and git.

## Quick start

```bash
adr init                                   # docs/adr/.template.md + 0001-record-architecture-decisions.md
adr new "Use PostgreSQL" --tag storage --scope "src/db/**"  # docs/adr/0002-use-postgresql.md (proposed)
adr accept 2
adr new "Use PostgreSQL 17" --supersedes 2 --accepted
adr list
adr graph --format mermaid                 # paste into any GitHub/GitLab Markdown file
adr check                                  # CI-friendly validation
```

## Tie decisions to code

Add `scope` globs to an ADR's frontmatter:

```yaml
scope: ["src/db/**", "migrations/**"]
```

Then:

```bash
adr for src/db/pool.py                     # which decisions govern this file?
adr check --diff origin/main --strict      # CI gate: changed files governed by ADRs in force
```

## History

Every read command accepts `--at REF`:

```bash
adr list --at v1.2 --status accepted       # what was in force at release 1.2?
adr log 7                                  # git history of ADR 0007
```

## For coding agents

Add one line to `AGENTS.md` (or your agent's equivalent):

```markdown
Run `adr prime` at the start of every session and follow the ADRs it lists.
```

`adr prime --budget 400` limits the briefing to about 400 words, picking the most important and most relevant decisions first (the top-scored ADR is always shown). `adr skill` prints a skill that teaches agents when and how to write ADRs; redirect it into your agent's skill directory (for example `adr skill > .claude/skills/adr/SKILL.md`).

## Commands

`adr --help` lists every command; the full specification is in [docs/SPEC.md](docs/SPEC.md).

## Licence

MIT
