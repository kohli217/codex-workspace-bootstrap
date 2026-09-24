# SARIF and GitHub Code Scanning

`codex-workspace-bootstrap` can emit SARIF 2.1.0 for the complete preflight.

## Recommended: comprehensive preflight SARIF

```powershell
cwb preflight . --sarif codex-workspace-bootstrap.sarif
```

The preflight SARIF can include:

- repository-readiness warnings;
- blocking tracked secret-risk filename findings;
- package-manager mismatch or conflicting package-manager evidence;
- same-scope instruction drift;
- referenced package scripts that do not exist;
- missing path-specific scope metadata.

Instruction-integrity results include the relevant instruction file as a SARIF location when one is available.

Passing checks are omitted. Blocking audit findings use SARIF level `error`; current instruction-integrity findings use `warning`.

The integrity lint reads supported instruction files locally to extract executable-looking commands. **It does not execute those commands.** Secret-risk filename checks do not read or include suspected secret-file contents.

## Audit-only compatibility mode

The earlier audit-only SARIF remains available:

```powershell
cwb audit . --sarif audit-only.sarif
```

Use `preflight --sarif` for new integrations.

## Upload to GitHub Code Scanning

```yaml
name: AI repository preflight

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  security-events: write

jobs:
  preflight:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
        with:
          python-version: "3.13"

      - name: Install
        run: python -m pip install codex-workspace-bootstrap

      - name: Generate comprehensive SARIF
        run: cwb preflight . --sarif codex-workspace-bootstrap.sarif

      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@1c5b675653bb5c22dbe9b12b556ec555138e09fd
        with:
          sarif_file: codex-workspace-bootstrap.sarif
          category: codex-workspace-bootstrap
```

The Marketplace Action can generate the same report through its `sarif` input.

For pull requests from forks, GitHub may restrict workflow token permissions. Keep permissions minimal and do not introduce secrets merely to upload results.

## Scope

SARIF makes deterministic repository-readiness and instruction-integrity findings visible in GitHub tooling. It does not turn the project into a comprehensive secret scanner or vulnerability scanner, and a clean report is not a security guarantee.
