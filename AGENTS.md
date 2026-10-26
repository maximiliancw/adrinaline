# Agent instructions

- Run `adr prime` at the start of every session and follow the ADRs it lists.
- Python 3.14 with uv. Before finishing: `uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest -q`.
- The specification is `docs/SPEC.md`; implementation plans are in `docs/superpowers/plans/`.
- Work on a short-lived branch, open a PR with `gh pr create`, then `gh pr merge --auto --rebase`; it merges once CI is green. Never push to `main`.
- Commit messages are Conventional Commits and decide the next version (ADR 0006): `feat` → minor, `fix` → patch, `docs`/`ci`/`chore`/`test`/`refactor` → no release.
