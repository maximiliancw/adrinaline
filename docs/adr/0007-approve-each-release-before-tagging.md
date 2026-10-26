---
status: accepted
date: 2026-10-26
scope: [.github/workflows/release.yml]
amends: [6]
---
# Approve each release before tagging

## Context and Problem Statement

Stolen maintainer credentials and compromised CI dependencies have been used to push malicious releases to PyPI through CI, which downstream auto-updates then install at once. ADR 0006 releases every warranting push to `main` without a human in the loop, so any code that reaches `main` or runs in the release workflow can publish.

## Considered Options

- Keep releases fully automatic; restrict the `pypi` environment to `main`
- Require the maintainer's approval in a `release` environment before the tag is pushed

## Decision Outcome

Chosen: approval before tagging. The release workflow runs as separate least-privilege jobs: `build` (read-only; computes the version, builds, writes commits, workflow changes and artifact SHA-256 to the job summary), `tag` (environment `release` with the maintainer as required reviewer; pushes the tag), `publish` (environment `pypi`, deployments limited to `main`, only `id-token: write`) and `github-release`. All actions are pinned to commit SHAs and `zizmor` checks the workflows on every PR.

### Consequences

- Each release costs one approval; an unexpected approval request is itself an alert.
- A rejected or expired approval leaves no tag and no package; a failed publish is retried with "Re-run failed jobs" for the same tag.
- The gate does not stop an attacker holding the maintainer's admin session or token; phishing-resistant 2FA on GitHub and PyPI and no long-lived tokens cover that.
