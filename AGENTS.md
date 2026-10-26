# Agent instructions

- Run `adr prime` at the start of every session and follow the ADRs it lists.
- Python 3.14 with uv. Before finishing: `uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest -q`.
- The specification is `docs/SPEC.md`.
- Work on a short-lived branch, open a PR with `gh pr create`, then `gh pr merge --auto --rebase`; it merges once CI is green. Never push to `main`.
- Commit messages are Conventional Commits; they decide the next version (ADR 0006).
- Create ADRs as `proposed`; only the maintainer accepts them. When an approved plan touches proposed ADRs, list them and ask whether to accept each one.
