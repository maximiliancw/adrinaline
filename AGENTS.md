# Agent instructions

- Run `adr prime` at the start of every session and follow the ADRs it lists.
- Python 3.14 with uv. Before finishing: `uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest -q`.
- The specification is `docs/SPEC.md`; implementation plans are in `docs/superpowers/plans/`.
