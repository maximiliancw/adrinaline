# Architecture Decision Records

The decisions governing this project. `docs/adr/` is scanned by the `adr`
CLI itself as the record store; this page is only the published index, kept
up to date by hand.

| ADR | Title |
|---|---|
| [0001](adr/0001-record-architecture-decisions.md) | Record architecture decisions |
| [0002](adr/0002-python-with-argparse-pydantic-and-ruamel-yaml.md) | Python with argparse, pydantic and ruamel.yaml |
| [0003](adr/0003-store-only-forward-relations-plus-superseded-by.md) | Store only forward relations plus superseded-by |
| [0004](adr/0004-read-only-git-integration.md) | Read-only git integration |
| [0005](adr/0005-cli-as-the-agent-interface.md) | CLI as the agent interface |
| [0006](adr/0006-release-from-main-with-commitizen-and-hatch-vcs.md) | Release from main with commitizen and hatch-vcs |
| [0007](adr/0007-approve-each-release-before-tagging.md) | Approve each release before tagging |
| [0008](adr/0008-track-decision-health-with-review-dates-and-scope-churn.md) | Track decision health with review dates and scope churn |
| [0009](adr/0009-cite-adrs-in-commit-trailers.md) | Cite ADRs in commit trailers |
| [0010](adr/0010-repair-mechanical-findings-with-adr-check-fix.md) | Repair mechanical findings with adr check --fix |
| [0011](adr/0011-extend-the-scopes-of-adrs-3-8-9-and-10-to-their-implementing-files.md) | Extend the scopes of ADRs 3, 8, 9 and 10 to their implementing files |
| [0012](adr/0012-give-adrs-1-2-4-5-and-6-a-scope.md) | Give ADRs 1, 2, 4, 5 and 6 a scope |

Run `adr index` for a machine-generated version of this table, or `adr list`
to include `proposed` and other non-`accepted` statuses.
