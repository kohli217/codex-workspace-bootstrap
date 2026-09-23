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
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
        with:
          python-version: "3.13"
      - uses: kohli217/codex-workspace-bootstrap@v0.11.0
        with:
          path: .
          strict: "true"
          fail_on_integrity: "true"
          require_ready: "true"
```

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `path` | `.` | Repository directory to check. |
| `strict` | `true` | Fail when a blocking audit finding is detected. |
| `fail_on_integrity` | `false` | Fail when any instruction-integrity finding is detected. |
| `require_ready` | `false` | Fail unless the final preflight state is exactly `READY`. |
| `sarif` | empty | Optional comprehensive SARIF 2.1.0 output path containing audit and instruction-integrity findings. |

## Outputs

`strict` only gates blocking audit findings, while `fail_on_integrity` gates instruction-integrity findings. Use `require_ready: "true"` when CI should also fail for other readiness gaps such as a missing README, manifest, .gitignore, or repository-wide AI instruction baseline.

The Action exposes structured outputs so later workflow steps can consume the same preflight result without parsing logs:

| Output | Description |
| --- | --- |
| `state` | `READY`, `NEEDS ATTENTION`, or `BLOCKED`. |
| `instruction_findings` | Number of instruction-integrity findings. |
| `blocking` | Number of blocking audit findings. |
| `warnings` | Number of audit warnings. |

Example:

```yaml
- id: cwb
  uses: kohli217/codex-workspace-bootstrap@v0.11.0
  with:
    path: .
    strict: "false"

- name: Report preflight state
  run: echo "state=${{ steps.cwb.outputs.state }}"
```

## What appears in the job summary

The Action writes a Markdown snapshot containing:

- READY / NEEDS ATTENTION / BLOCKED state;
- detected project signals;
- detected AI instruction/config files and their inferred scopes;
- audit totals;
- instruction-integrity finding/drift/invalid-command/metadata totals;
- detailed integrity findings;
- prioritized next actions.

## SARIF

```yaml
- uses: kohli217/codex-workspace-bootstrap@v0.11.0
  with:
    path: .
    strict: "true"
    sarif: codex-workspace-bootstrap.sarif
```

The generated SARIF contains both audit and instruction-integrity findings. Upload it with `github/codeql-action/upload-sarif@1c5b675653bb5c22dbe9b12b556ec555138e09fd` when GitHub Code Scanning integration is desired.

## Safety

The Action installs the code contained in the referenced release tag, runs local deterministic checks, and does not upload repository contents or suspected secret-file contents.

For reproducibility, pin this project to a release tag rather than `@main`. Third-party GitHub Actions in the examples are pinned to immutable commit SHAs.


## Scope-aware behavior

The integrity lint distinguishes repository-wide instructions from nested/path-specific rules. Common `applyTo` and `globs` frontmatter is used to infer a static scope prefix. Drift comparisons are conservative and do not treat unrelated scopes as if they were global instructions. Path-specific rules are validated against repository evidence but excluded from cross-file drift comparison when their full selector semantics cannot be represented safely.
