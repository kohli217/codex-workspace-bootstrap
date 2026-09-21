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
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - uses: kohli217/codex-workspace-bootstrap@v0.1.0
        with:
          path: .
          strict: "true"
```

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `path` | `.` | Repository directory to audit. |
| `strict` | `true` | Fail the action when blocking findings are detected. |

## What the action does

1. verifies that Python is available;
2. installs the version of `codex-workspace-bootstrap` contained in the referenced action tag;
3. runs the local repository audit;
4. returns the CLI exit code to the workflow.

The action does not upload repository contents or secret-file contents.

## Pinning

For reproducible CI, use a release tag such as `@v0.1.0` rather than `@main`. Review release notes before upgrading.
