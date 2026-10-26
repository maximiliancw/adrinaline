---
status: accepted
date: 2026-10-26
depends-on: [2]
---
# CLI as the agent interface

## Context and Problem Statement

Coding agents need to read and write ADRs reliably.

## Considered Options

* CLI with `--json`, `adr prime` and a bundled skill
* An MCP server

## Decision Outcome

Chosen option: "CLI with `--json`, `adr prime` and a bundled skill", because every agent can run shell commands, and JSON output plus stable error codes make the CLI machine-friendly without another server.

### Consequences

* Good, because there is one interface to test and document.
* Bad, because agents without shell access cannot use `adr`.
