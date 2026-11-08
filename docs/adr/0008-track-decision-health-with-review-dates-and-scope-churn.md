---
status: proposed
date: 2026-11-08
tags: [process]
scope: [src/adrinaline/check.py, src/adrinaline/model.py, src/adrinaline/prime.py]
depends-on: [4]
---
# Track decision health with review dates and scope churn

# Track decision health with review dates and scope churn

## Context and Problem Statement

ADRs rot silently. The decision stays accepted while the assumptions behind it change and the code it governs is rewritten. No surveyed ADR tool makes that drift visible, and nothing in adrinaline distinguishes an ADR reviewed last month from one nobody has looked at since it was written. How can the tool make the health of a decision measurable, deterministically and from git alone?

## Considered Options

- Record review dates in frontmatter (`review-by`, `reviewed`, `revisit-if`) and derive churn from git history over the ADR's `scope` (this ADR)
- Infer a review from the last commit that touched the ADR file, with no new keys
- Semantic drift detection with an LLM comparing the ADR text against the code
- Leave health to the team's process and change nothing

## Decision Outcome

Chosen: review dates plus scope churn. Three optional frontmatter keys: `review-by` (ISO date), `reviewed` (ISO date of the last review) and `revisit-if` (free text naming the assumption that would invalidate the decision). The drift baseline of an ADR is the later of `date` and `reviewed`; its churn is the number of non-merge commits since that baseline that touched a file matching its `scope`. `adr drift` reports churn per ADR in force; `adr review REF [--until DATE]` records a review; `adr check` warns `review-overdue` when `review-by` has passed and `stale-decision` when churn reaches the `drift-commits` threshold configured in `.adrinaline.toml` or `[tool.adrinaline]` (default 0, off); `adr prime` lists ADRs that need review.

Inferring reviews from the ADR file's history was rejected because a typo fix would reset the clock and the signal is lost in `--at` reads. LLM comparison was rejected because it is non-deterministic and needs a model at check time, which breaks the CI story. Doing nothing leaves the central complaint about ADRs unanswered.

### Consequences

- Teams can make staleness a CI signal with one config key, and agents see overdue decisions at session start.
- Three new frontmatter keys and one config key widen the format; all are optional and hand-editable, so existing sets stay valid.
- Churn counts commits, not meaning: a large refactor of a governed file counts the same as a rename. The threshold is per repository, not per ADR.
- Git remains read-only (ADR 0004); `adr drift` and `stale-decision` need a repository and degrade silently without one.
