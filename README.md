# codex-workspace-bootstrap

[![CI](https://github.com/kohli217/codex-workspace-bootstrap/actions/workflows/ci.yml/badge.svg)](https://github.com/kohli217/codex-workspace-bootstrap/actions/workflows/ci.yml)
[![CodeQL](https://github.com/kohli217/codex-workspace-bootstrap/actions/workflows/codeql.yml/badge.svg)](https://github.com/kohli217/codex-workspace-bootstrap/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/kohli217/codex-workspace-bootstrap)](https://github.com/kohli217/codex-workspace-bootstrap/releases/latest)
[![License](https://img.shields.io/github/license/kohli217/codex-workspace-bootstrap)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

Make Windows repositories **Codex-ready** with automated environment checks, project instructions, safety audits, and maintainer workflows.

[日本語ガイド](docs/README.ja.md) · [Examples](docs/EXAMPLES.md) · [Roadmap](docs/ROADMAP.md) · [Releases](https://github.com/kohli217/codex-workspace-bootstrap/releases)

> Community-maintained project. It is not an official OpenAI product and is not affiliated with OpenAI.

## What problem does it solve?

Codex works better when a repository clearly states its toolchain, validation commands, constraints, and maintenance workflow. On Windows, those details are often scattered across README files, shell history, and machine-specific assumptions.

`codex-workspace-bootstrap` gives maintainers one repeatable entry point to:

- audit Git, Python, Node.js, npm, PowerShell, WSL, and Codex availability;
- inspect repository basics such as README, license, ignore rules, manifests, and `AGENTS.md`;
- warn about common secret-bearing filenames without reading their contents;
- distinguish tracked risky files from ignored or untracked files when Git is available;
- generate a project-aware `AGENTS.md` for Python, Node.js, mixed, or unknown projects;
- write a machine-readable JSON report;
- fail CI on blocking findings with `--strict`;
- validate releases through automated tests, self-audit, and build checks.

## 30-second start

Install the pinned v0.2.0 wheel:

```powershell
py -m pip install "https://github.com/kohli217/codex-workspace-bootstrap/releases/download/v0.2.0/codex_workspace_bootstrap-0.2.0-py3-none-any.whl"
```

Audit the current repository:

```powershell
codex-workspace-bootstrap audit .
```

Generate project instructions:

```powershell
codex-workspace-bootstrap init-agents .
```

Check the installed version:

```powershell
codex-workspace-bootstrap --version
```

For more examples, see [docs/EXAMPLES.md](docs/EXAMPLES.md).

## Why a pinned release instead of `irm ... | iex`?

The recommended quick start installs a specific published wheel so users can see exactly which release they are installing. A PowerShell helper script remains available in [scripts/install.ps1](scripts/install.ps1), but piping remote scripts directly into PowerShell is not the recommended path.

## GitHub Action

Use the tool directly in an OSS repository workflow:

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-python@v5
  with:
    python-version: "3.13"
- uses: kohli217/codex-workspace-bootstrap@v0.2.0
  with:
    path: .
    strict: "true"
```

See [docs/GITHUB_ACTION.md](docs/GITHUB_ACTION.md) for the full workflow and input reference.

## Commands

### Audit a repository

```powershell
codex-workspace-bootstrap audit .
```

Write JSON output:

```powershell
codex-workspace-bootstrap audit . --json audit-report.json
```

Use strict mode in CI:

```powershell
codex-workspace-bootstrap audit . --strict
```

### Generate `AGENTS.md`

```powershell
codex-workspace-bootstrap init-agents .
```

The generator inspects common project manifests and layout signals, then writes conservative validation guidance. Existing `AGENTS.md` files are never overwritten unless `--force` is explicit.

## Safety model

- The core audit path performs local inspection only.
- The tool does **not** read or print the contents of suspected secret files.
- The tool does **not** send repository contents to a remote service.
- A passing audit is evidence about the checks performed, **not** a security guarantee.
- File modifications are opt-in; existing `AGENTS.md` files are protected by default.

See [SECURITY.md](SECURITY.md) for reporting guidance.

## Maintainer workflow

This project uses an issue → branch → pull request → CI → merge → release workflow.

Current automated checks include:

- Windows and Ubuntu test matrices on Python 3.10 and 3.13;
- built-wheel smoke testing;
- strict self-audit before releases;
- CodeQL static analysis;
- weekly dependency update checks for Python and GitHub Actions;
- validated one-click GitHub releases with attached wheel and source distribution.

Release history began with [v0.1.0](https://github.com/kohli217/codex-workspace-bootstrap/releases/tag/v0.1.0).

## Codex-oriented workflow

A practical repository workflow is:

1. run `audit`;
2. review warnings and blocking findings;
3. generate or review `AGENTS.md`;
4. give Codex a scoped issue or task;
5. run the repository tests and the audit again;
6. inspect the diff before merge;
7. release only after CI passes.

See [AGENTS.md](AGENTS.md) for this repository's own agent instructions and [skills/codex-workspace-bootstrap/SKILL.md](skills/codex-workspace-bootstrap/SKILL.md) for the reusable skill.

## Project scope

### In scope

- Windows-first repository readiness checks;
- Codex-oriented project instructions;
- maintainer automation that is deterministic and reviewable;
- CI-friendly reporting and safe defaults.

### Not in scope

- claiming that a repository is secure because an audit passed;
- silently changing user configuration;
- uploading repository contents by default;
- replacing project-specific documentation or human review.

## Development

```powershell
git clone https://github.com/kohli217/codex-workspace-bootstrap.git
cd codex-workspace-bootstrap
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e . pytest
pytest -q
```

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and [SUPPORT.md](SUPPORT.md).

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md).

## Releasing

Maintainers can create a tested GitHub release from the Actions UI. See [docs/RELEASING.md](docs/RELEASING.md).

## Citation

Machine-readable citation metadata is available in [CITATION.cff](CITATION.cff).

## License

MIT. See [LICENSE](LICENSE).
