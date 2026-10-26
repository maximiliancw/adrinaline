---
status: accepted
date: 2026-10-26
tags: [release]
depends-on: [2]
---
# Release from main with commitizen and hatch-vcs

## Context and Problem Statement

Releases should be fully automatic for a solo maintainer, follow semantic versioning from Conventional Commits, and never break `uv.lock` or loop on bump commits pushed by CI.

## Considered Options

- `uv_build` with a static version; CI runs `cz bump` and pushes a bump commit to main
- `uv_build`; CI keeps a release PR up to date, merging it releases
- `hatchling` + `hatch-vcs`; the git tag is the only version, CI tags and publishes

## Decision Outcome

Chosen: `hatchling` + `hatch-vcs`. Every push to `main` runs `cz bump --get-next`; if the commits warrant a bump, the job tags, builds, publishes to PyPI via trusted publishing and creates a GitHub Release whose notes are `cz changelog` for that tag. `major_version_zero` keeps breaking changes on minor bumps until 1.0 is released deliberately. Checks run only on pull requests; branch protection requires an up-to-date branch, so main is never re-checked.

### Consequences

- CI never commits, needs no personal token, and `uv.lock` never changes on release.
- There is no `CHANGELOG.md`; GitHub Releases hold the changelog.
- `uv version --bump` no longer applies; the build backend is not `uv_build`.
- Commit messages are part of the release interface; `cz check` gates them on every PR.
