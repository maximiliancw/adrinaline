# Contributing

Bug reports, feature requests and questions go to [GitHub Issues](https://github.com/maximiliancw/adrinaline/issues). Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md), never in a public issue.

## Changes

1. Fork the repository and work on a short-lived branch.
2. Open a pull request against `main`. It merges by rebase once CI is green; `main` takes no direct pushes.
3. Behavior is specified in [docs/SPEC.md](docs/SPEC.md). A change to behavior updates the spec in the same pull request.

## Requirements for a pull request

- **Commit messages** follow [Conventional Commits](https://www.conventionalcommits.org/). They decide the next version and the release notes, so `feat:`, `fix:` and `!` for breaking changes matter.
- **ADRs.** Run `uv run adr for <path>` before changing a file and follow the decisions it lists. Cite them in a commit trailer (`ADR: 3`), or give `ADR-Exempt: <reason>` for a change to governed files that follows none. A decision that is expensive to reverse gets a new ADR (`uv run adr new`), which starts as `proposed`.
- **Tests.** Every new feature and every bug fix comes with a test that fails without it. Coverage must stay at or above the floor in `pyproject.toml`.
- **Checks.** The pull request must pass the same gate as CI. CI runs the commit-stage hooks of `prek.toml`; installed locally, they run on commit and the tests, ADR trailers and docs build run on push. Run them by hand with `uv run prek run --all-files`.

The project uses Python 3.14 and [uv](https://docs.astral.sh/uv/). Set up with:

```sh
uv sync                # development tools, including prek
uv run prek install    # Git hooks (prek.toml)
```
