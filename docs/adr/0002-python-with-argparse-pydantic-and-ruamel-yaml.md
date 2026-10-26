---
status: accepted
date: 2026-10-26
---
# Python with argparse, pydantic and ruamel.yaml

## Context and Problem Statement

The maintainer reviews all code and has no Go experience. A single binary is desirable but not required.

## Considered Options

* Python 3.14 with uv, argparse, pydantic, ruamel.yaml
* TypeScript compiled with Bun
* Go

## Decision Outcome

Chosen option: "Python 3.14 with uv, argparse, pydantic, ruamel.yaml", because it is the easiest to review and distribute via `uv tool install`.

### Consequences

* Good, because round-trip YAML keeps hand edits intact.
* Bad, because there is no standalone binary in v1.
