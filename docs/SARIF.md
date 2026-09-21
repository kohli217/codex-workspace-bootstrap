# SARIF and GitHub Code Scanning

`codex-workspace-bootstrap` can write warnings and blocking findings as SARIF 2.1.0.

## Generate a SARIF report

```powershell
codex-workspace-bootstrap audit . --sarif codex-workspace-bootstrap.sarif
```

Passing checks are omitted. Non-blocking findings use SARIF level `warning`; blocking findings use `error`.

The report contains finding messages and stable rule IDs. The audit does not read or include the contents of suspected secret files.

## Upload to GitHub Code Scanning

A repository can opt in with a workflow such as:

```yaml
name: Codex workspace security audit

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  security-events: write

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.13"

      - name: Install codex-workspace-bootstrap
        run: >-
          python -m pip install
          "https://github.com/kohli217/codex-workspace-bootstrap/releases/download/v0.3.0/codex_workspace_bootstrap-0.3.0-py3-none-any.whl"

      - name: Generate SARIF
        run: codex-workspace-bootstrap audit . --sarif codex-workspace-bootstrap.sarif

      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v4
        with:
          sarif_file: codex-workspace-bootstrap.sarif
          category: codex-workspace-bootstrap
```

For pull requests from forks, GitHub may restrict the token permissions available to workflows. Keep the workflow permissions minimal and do not introduce secrets merely to upload audit results.

## Scope

SARIF integration makes repository-readiness findings visible in security tooling. It does not turn the audit into a comprehensive secret scanner or vulnerability scanner, and a clean report is not a security guarantee.
