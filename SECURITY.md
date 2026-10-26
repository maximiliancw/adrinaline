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

Each GitHub Release also includes a CycloneDX SBOM (`sbom.cdx.json`) of the runtime dependencies.
