# GitHub Action

The Marketplace Action runs the repository preflight during CI and surfaces a human-readable report in the GitHub Actions **Job Summary**.

## Basic workflow

```yaml
name: AI repository preflight

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  preflight:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.13"
      - uses: kohli217/codex-workspace-bootstrap@v0.5.0
        with:
          path: .
          strict: "true"
          fail_on_drift: "true"
```

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `path` | `.` | Repository directory to check. |
| `strict` | `true` | Fail when a blocking audit finding is detected. |
| `fail_on_drift` | `false` | Fail when cross-agent instruction drift or invalid package scripts are detected. |
| `sarif` | empty | Optional SARIF 2.1.0 output path. |

## What appears in the job summary

The Action writes a Markdown snapshot containing:

- READY / NEEDS ATTENTION / BLOCKED state;
- detected project signals;
- detected AI instruction/config files and their inferred scopes;
- audit totals;
- instruction-integrity finding/drift/invalid-command totals;
- detailed integrity findings;
- prioritized next actions.

## SARIF

```yaml
- uses: kohli217/codex-workspace-bootstrap@v0.5.0
  with:
    path: .
    strict: "true"
    sarif: codex-workspace-bootstrap.sarif
```

Upload the generated SARIF with `github/codeql-action/upload-sarif@v4` when GitHub Code Scanning integration is desired.

## Safety

The Action installs the code contained in the referenced release tag, runs local deterministic checks, and does not upload repository contents or suspected secret-file contents.

For reproducibility, pin a release tag rather than `@main`.


## Scope-aware behavior

The integrity lint distinguishes repository-wide instructions from nested/path-specific rules. Common `applyTo` and `globs` frontmatter is used to infer a static scope prefix. Drift comparisons are conservative and do not treat unrelated scopes as if they were global instructions.
