# GitHub Action

`codex-workspace-bootstrap` can be used directly from GitHub Actions to audit a repository during CI.

## Basic workflow

```yaml
name: Codex workspace audit

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.13"
      - uses: kohli217/codex-workspace-bootstrap@v0.3.0
        with:
          path: .
          strict: "true"
```

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `path` | `.` | Repository directory to audit. |
| `strict` | `true` | Fail the action when blocking findings are detected. Must be `true` or `false`. |
| `sarif` | empty | Optional output path for a SARIF 2.1.0 report. |

## SARIF example

```yaml
- uses: kohli217/codex-workspace-bootstrap@v0.3.0
  with:
    path: .
    strict: "true"
    sarif: codex-workspace-bootstrap.sarif
```

The generated SARIF file can be uploaded with `github/codeql-action/upload-sarif@v4`. See [SARIF.md](SARIF.md).

## What the action does

1. verifies that Python is available;
2. installs the version of `codex-workspace-bootstrap` contained in the referenced action tag;
3. validates Action inputs;
4. runs the local repository audit;
5. optionally writes SARIF;
6. returns the CLI exit code to the workflow.

The action does not upload repository contents or secret-file contents.

## Pinning

For reproducible CI, use a release tag such as `@v0.3.0` rather than `@main`. Review release notes before upgrading.

## GitHub Marketplace

This repository is structured as a single reusable Action with its metadata in the root `action.yml`. Marketplace publication is performed from a tagged GitHub release after tests pass.
