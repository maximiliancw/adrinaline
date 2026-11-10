# Security policy

## Supported versions

Only the latest release receives fixes.

## Reporting a vulnerability

Report it privately through [GitHub's private vulnerability reporting](https://github.com/maximiliancw/adrinaline/security/advisories/new). Please do not open a public issue.

## Verifying a release

Every release is built in GitHub Actions, approved by the maintainer and published to PyPI via trusted publishing. Each artifact carries a build provenance attestation:

```sh
pip download adrinaline --no-deps -d dist
gh attestation verify dist/* --repo maximiliancw/adrinaline
```

Each GitHub Release also includes a CycloneDX SBOM (`sbom.cdx.json`) of the runtime dependencies and `provenance.sigstore.json`, the Sigstore bundle of the attestation; add `--bundle provenance.sigstore.json` to the command above to verify against the downloaded bundle instead of fetching the attestation from GitHub.

## Repository protection

The `main` branch is covered by an active repository ruleset with no bypass actors:

- Changes land only through a pull request, merged by rebase.
- The status checks `test (ubuntu-latest)`, `test (macos-latest)`, `lint` and `docs` must pass, and the branch must be up to date with `main` before merging.
- History stays linear.
- Deleting the branch and force-pushing to it are blocked.
- Each release needs the maintainer's approval in the `release` environment.

Required human reviews are off (zero approvals) because the project has a single maintainer.
