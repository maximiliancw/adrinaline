---
status: accepted
date: 2026-10-26
decision-makers: [Max Wolf]
---
# Record architecture decisions

## Context and Problem Statement

We need to record the architecturally significant decisions made in this project, so that people and coding agents can understand why the system is built the way it is.

## Considered Options

* Architecture Decision Records (ADRs) in MADR 4 format, managed with `adr`
* Decisions kept only in issues, wiki pages or commit messages

## Decision Outcome

Chosen option: "ADRs in MADR 4 format, managed with `adr`", because they live next to the code, are reviewed like code, and can be queried by humans and agents.

* Each ADR is a Markdown file `NNNN-slug.md` in this directory, with YAML frontmatter for status, date and relations.
* Accepted ADRs are immutable except for their status and relations. A changed decision gets a new ADR that supersedes or amends the old one.
* `adr check` passes before changes are merged.

### Consequences

* Good, because decisions and their reasons are versioned with the code.
* Bad, because writing an ADR takes time, so ADRs stay short.
