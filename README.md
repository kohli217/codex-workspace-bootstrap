# codex-workspace-bootstrap

[![CI](https://github.com/kohli217/codex-workspace-bootstrap/actions/workflows/ci.yml/badge.svg)](https://github.com/kohli217/codex-workspace-bootstrap/actions/workflows/ci.yml)
[![CodeQL](https://github.com/kohli217/codex-workspace-bootstrap/actions/workflows/codeql.yml/badge.svg)](https://github.com/kohli217/codex-workspace-bootstrap/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/kohli217/codex-workspace-bootstrap/badge)](https://scorecard.dev/viewer/?uri=github.com/kohli217/codex-workspace-bootstrap)
[![Release](https://img.shields.io/github/v/release/kohli217/codex-workspace-bootstrap)](https://github.com/kohli217/codex-workspace-bootstrap/releases/latest)
[![PyPI](https://img.shields.io/pypi/v/codex-workspace-bootstrap)](https://pypi.org/project/codex-workspace-bootstrap/)
[![License](https://img.shields.io/github/license/kohli217/codex-workspace-bootstrap)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

**Preflight your repository before an AI coding agent touches it — and catch instruction drift before different agents follow different rules.**

Windows-first. Local by default. CI-friendly. Designed for repositories used with Codex, Copilot, Cline, Claude Code, Gemini CLI, Continue, Cursor, Windsurf, and similar coding agents.

[日本語ガイド](docs/README.ja.md) · [Examples](docs/EXAMPLES.md) · [GitHub Action](docs/GITHUB_ACTION.md) · [GitHub App](docs/GITHUB_APP.md) · [Marketplace](docs/GITHUB_MARKETPLACE.md) · [Privacy](PRIVACY.md) · [Free GitHub App deployment](deploy/cloudflare/README.md) · [Cloud Run alternative](deploy/cloudrun/README.md) · [Integration contract](docs/INTEGRATIONS.md) · [Stability](docs/STABILITY.md) · [Roadmap](docs/ROADMAP.md) · [Releases](https://github.com/kohli217/codex-workspace-bootstrap/releases)

> Community-maintained project. Not an official OpenAI product and not affiliated with OpenAI.

## Why add this to your repository?

AI coding agents can move fast, but they can also follow stale or conflicting repository instructions. `codex-workspace-bootstrap` adds one repeatable check before that happens.

| Common failure | What `cwb` does |
| --- | --- |
| One instruction says `npm`, another says `pnpm` | Flags the mismatch before an agent edits the repository. |
| An instruction tells the agent to run a test/lint script that does not exist | Reports the invalid command instead of letting the mistake reach the agent. |
| A risky file such as `.env.production` is Git-tracked | Surfaces it as a blocking risk signal without printing its contents. |
| The repository is still missing important readiness pieces | `cwb preflight . --require-ready` can fail CI until the repository reaches `READY`. |

It is local-first: the core preflight does not send repository contents to a remote AI service.

## The 20-second demo

```powershell
py -m pip install codex-workspace-bootstrap
cwb preflight .
```

Typical output:

```text
AI Repository Preflight
State: NEEDS ATTENTION
Project: Python
AI instructions: none detected
Audit: 10 passed, 4 warnings, 0 blocking
Instruction integrity: 0 findings, 0 drift, 0 invalid commands, 0 metadata
Next actions:
  [P1] Add repository instructions for AI coding agents -> cwb init-agents .
  [P2] Make the Codex CLI available when local Codex workflows are intended -> codex --version
```

Fix the highest-value gap:

```powershell
cwb init-agents .
cwb preflight .
```

### See it catch real mistakes

A reproducible demo creates a temporary repository where the project uses **pnpm** but `AGENTS.md` tells the agent to use **npm** and references a nonexistent `lint` script.

```powershell
py examples/first-run-demo/run_demo.py
```

Expected outcome:

```text
=== BEFORE ===
State: NEEDS ATTENTION
Findings:
  - package-manager-mismatch
  - missing-package-script

=== AFTER ===
State: READY
Findings: none

Demo verification: PASS
```

See [examples/first-run-demo](examples/first-run-demo) for the full reproducible demo. It uses disposable temporary Git repositories and is verified in CI.

### See multi-agent Python drift

A second reproducible demo shows same-scope validation drift between multiple coding agents without confusing it with a path-specific rule:

```powershell
py examples/multi-agent-python-demo/run_demo.py
```

The root `AGENTS.md` uses `mypy src`, while `CLAUDE.md` initially uses `pyright src`. A Copilot rule scoped to `tests/**/*.py` separately uses `ruff check tests` and is not falsely compared as a repository-wide peer. After Claude switches to the wrapper-equivalent `python -m mypy src`, the temporary repository reaches `READY`.

See [examples/multi-agent-python-demo](examples/multi-agent-python-demo). The demo is network-free, does not execute commands extracted from instruction files, and is verified in CI on Windows and Ubuntu.

### Try it on your repository

```powershell
py -m pip install codex-workspace-bootstrap
cwb preflight .
```

If the result is useful, noisy, or surprising, open a [Usage report](https://github.com/kohli217/codex-workspace-bootstrap/issues/new?template=usage_report.yml). Public references are optional; do not include private repository contents, credentials, or secret values.

Useful feedback includes false positives, missing repository layouts, monorepo behavior, and which check saved you time.

The goal is not a vanity score. The result is one of:

- **READY** — core repository signals and AI instructions are present, with no blocking finding;
- **NEEDS ATTENTION** — usable, but important repository or AI-instruction signals are missing;
- **BLOCKED** — a blocking finding such as a tracked secret-risk filename needs review.

## What it checks

### Repository readiness

- Git repository
- README
- license
- `.gitignore`
- common project manifests, including Python, Node.js, Go, Rust, JVM, and .NET roots
- local Git / Python / Node.js / repository-selected package manager / PowerShell / WSL / Codex signals

### AI instruction coverage

The preflight detects repository instruction/config signals for:

- **Codex / OpenAI agents** — `AGENTS.md`
- **GitHub Copilot** — repository instructions
- **Cline**
- **Claude Code**
- **Gemini CLI**
- **Continue**
- **Cursor**

It does not claim these files are correct merely because they exist. It tells you what was detected so a maintainer can review the actual instructions.

### Cross-agent instruction integrity

When multiple AI instruction files exist, `cwb` reads executable-looking commands and checks them against repository evidence. It understands nested `AGENTS.md` / `AGENTS.override.md`, nested `CLAUDE.md`, Gemini CLI hierarchical context files (including project `context.fileName` overrides), nested Cursor `.cursor/rules`, and common path-specific frontmatter such as Copilot `applyTo` and rule `globs`. It can flag:

- package-manager mismatches against `packageManager` and lockfiles;
- cross-agent package-manager drift;
- missing `package.json` scripts referenced by instructions;
- conflicting test/lint/build/typecheck/check validation commands when instruction files have no shared command for the same validation family; common Python workflows such as `ruff check`, `mypy`, `pyright`, `tox`, `nox`, and `pre-commit run` are normalized across direct, `python -m`, `uv run`, `poetry run`, and `pdm run` forms where applicable.

The lint is intentionally conservative: different files may contain additional commands without being treated as conflicts when they share a compatible validation baseline. Commands from different scopes are not compared as if they were global rules. Path-specific rules are validated individually against repository evidence but are not cross-compared for drift unless their full selector semantics can be represented safely. A repository is not marked READY when it only has nested/path-specific instructions and no repository-wide instruction baseline.

### Risk signals

The audit warns about common secret-bearing filenames without printing their contents, including environment-specific `.env.*` files while excluding common template names such as `.env.example` and `.env.sample`. When Git is available, it distinguishes **tracked**, **ignored**, and **untracked/unknown** candidates. Tracked risky filenames can become blocking findings in strict mode.

This is intentionally a lightweight preflight check, not a replacement for deep scanners such as Gitleaks or Trivy.

## Why this exists

AI coding tools are good at editing code. They are not a substitute for repository hygiene.

Before handing a repository to an agent, maintainers still need answers to questions such as:

- Is this the right repository root?
- Is the expected toolchain available?
- Does the repository explain how to validate changes?
- Are AI instructions present?
- Are risky files accidentally tracked?
- Can CI surface the same checks for every pull request?

`codex-workspace-bootstrap` turns those questions into one repeatable preflight.

## Short CLI

The package installs both command names:

```powershell
cwb --version
codex-workspace-bootstrap --version
```

Use `cwb` for day-to-day work.

## Commands

### One-command preflight

```powershell
cwb preflight .
```

Write reports for automation or review:

```powershell
cwb preflight . --json preflight.json
cwb preflight . --markdown preflight.md
cwb preflight . --sarif preflight.sarif
```

Use strict mode when blocking findings should return a non-zero exit code:

```powershell
cwb preflight . --strict
```

Fail CI on any instruction-integrity finding:

```powershell
cwb preflight . --fail-on-integrity
```

Require the full preflight state to be `READY`:

```powershell
cwb preflight . --require-ready
```

Use `--require-ready` when CI should reject both `NEEDS ATTENTION` and `BLOCKED`, including missing repository-wide AI instructions or essential repository markers.

For a remote service such as a GitHub App, skip host-machine tool availability checks while keeping repository evidence, Git tracking, risk filenames, and instruction integrity checks:

```powershell
cwb preflight . --repository-only
```

This prevents a remote scanner from reporting the scanner host's Node.js, package-manager, WSL, PowerShell, or Codex availability as if it belonged to the inspected repository.

### Machine-readable schemas

Inspect the stable JSON Schema contracts used by integrations and repository policy:

```powershell
cwb schema preflight
cwb schema config
```

The preflight report currently uses `schema_version: 1`; root `.cwb.json` uses `version: 1`. Breaking machine-contract changes require a new version rather than silently reinterpreting an existing one. See [docs/SCHEMAS.md](docs/SCHEMAS.md).

### Explicit repository suppressions

If a repository intentionally triggers a known non-blocking preflight warning, add a root `.cwb.json` with a narrow, documented suppression:

```json
{
  "version": 1,
  "suppress": {
    "checks": [
      {
        "name": "license",
        "reason": "This internal repository intentionally has no standalone license file."
      }
    ],
    "instruction_findings": [
      {
        "kind": "validation-command-drift",
        "path": "CLAUDE.md",
        "scope": ".",
        "reason": "Claude intentionally runs a narrower smoke suite."
      }
    ]
  }
}
```

Suppressions are fail-closed and auditable. Every entry requires a reason, instruction suppressions require an exact repository-relative file path, and applied or unused entries remain visible in the preflight report. Blocking checks, essential readiness checks, tracked secret-risk findings, wildcard paths, and error-severity instruction findings cannot be suppressed. Invalid or unsafe `.cwb.json` configuration makes preflight `NEEDS ATTENTION`.

The raw `cwb audit` command is intentionally unsuppressed. Repository suppressions apply to the shared `preflight` contract used by the CLI, reusable Action, and GitHub App. Because `.cwb.json` is repository policy and is evaluated from the inspected revision, changes to it should be reviewed like CI or branch-policy changes. GitHub Checks add a notice on `.cwb.json` whenever a suppression is actually applied.

### Detailed audit

```powershell
cwb audit .
cwb audit . --json audit.json
cwb audit . --sarif audit.sarif
cwb audit . --strict
```

### Safe fix preview

```powershell
cwb fix .
```

This is preview-only by default. To apply only low-risk supported fixes:

```powershell
cwb fix . --apply
```

Existing conflicting instruction files are never auto-rewritten. They remain human-review findings.

### Non-destructive doctor

```powershell
cwb doctor .
```

`doctor` prints remediation guidance only. It does not install software or modify system configuration.

### Generate `AGENTS.md`

```powershell
cwb init-agents .
```

Generation is evidence-based: the tool identifies common Python, Node.js, Go, Rust, JVM, and .NET project roots, then only emits validation commands that have direct repository evidence. Python/Node-specific validation is cross-checked against package-manager evidence, package scripts, pytest configuration, and README commands. Plausible but unconfirmed commands are separated for maintainer review. Existing `AGENTS.md` files are never overwritten unless `--force` is explicit.

## GitHub Action

The reusable Action is published on GitHub Marketplace.

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
- uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
  with:
    python-version: "3.13"
- uses: kohli217/codex-workspace-bootstrap@v1.0.0
  with:
    path: .
    strict: "true"
    fail_on_integrity: "true"
    require_ready: "true"
```

The Action adds the preflight Markdown report to the **GitHub Actions job summary**, so maintainers get a readable readiness snapshot without digging through raw logs. Optional SARIF output contains both repository-audit and instruction-integrity findings and can be uploaded to GitHub Code Scanning.

See [docs/GITHUB_ACTION.md](docs/GITHUB_ACTION.md).

Read-only evaluations against real public repositories are documented in [docs/PUBLIC_REPO_EVALUATIONS.md](docs/PUBLIC_REPO_EVALUATIONS.md). They are reproducible technical evaluations, not claims of third-party adoption.

## GitHub App

**Public App:** [CWB Preflight](https://github.com/apps/cwb-preflight) · [Install](https://github.com/apps/cwb-preflight/installations/new)

For public OSS repositories, CWB can also run as a self-hosted GitHub App. A verified `push` or `pull_request` event triggers repository-only preflight against the exact event revision and publishes a **CWB Preflight** Check Run on that commit. File-backed instruction-integrity findings and tracked secret-risk filenames are surfaced as file-level Check annotations, without adding repository permissions or reading secret-file contents.

The verified zero-cost public-OSS deployment uses:

```text
GitHub App
  -> Cloudflare Worker + Queue (Free)
  -> GitHub Actions in this public repository
  -> short-lived repository-scoped installation token
  -> CWB Preflight Check
```

This path does not require a Google Cloud billing account. It is intentionally **public-repository-only**: private-repository events are rejected before they are queued into the public Actions worker.

The App keeps the minimum repository permissions documented by the project: Checks read/write, Contents read-only, and Pull requests read-only.

The current public App has been revalidated after promotion: the renamed `CWB Preflight` App produced a successful `READY` Check Run through the full Cloudflare → Queue → GitHub Actions → installation-token → exact-revision checkout path.

See [docs/GITHUB_APP.md](docs/GITHUB_APP.md) for the integration contract and [deploy/cloudflare/README.md](deploy/cloudflare/README.md) for the completely free deployment.

## Integration boundary

The CLI, reusable GitHub Action, GitHub App, and future AI-agent skills share one preflight engine and one policy evaluator. Machine-readable reports declare a schema version so integrations can detect incompatible changes instead of silently drifting.

See [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md). The minimum GitHub App permissions and webhook subscriptions are defined in [docs/GITHUB_APP.md](docs/GITHUB_APP.md) and mirrored by code-level regression tests.

## Where it fits

This project is a **preflight layer**, not an AI coding agent and not a deep security scanner.

| Need | Use |
| --- | --- |
| Edit or generate code | Codex, Copilot, Cline, Claude Code, Continue, etc. |
| Deep secret/vulnerability scanning | Gitleaks, Trivy, dedicated security tooling |
| Reproducible toolchain management | Dev Containers, mise, project-specific tooling |
| **Check whether a repository is ready before AI coding starts** | **codex-workspace-bootstrap** |

The intent is to complement those tools, not replace them.

## Safety model

- Core checks run locally.
- Suspected secret files are not opened or printed by the filename-risk check.
- Repository contents are not sent to a remote AI service by the core audit.
- Instruction files are read locally for deterministic linting; extracted commands are never executed by the integrity lint.
- Repository instruction/configuration and project-marker contents are not trusted through symbolic links. CWB may recognize the exact lexical aliases `CLAUDE.md -> AGENTS.md` and `GEMINI.md -> AGENTS.md` (or `./AGENTS.md`) only when the sibling `AGENTS.md` is a regular file; linting reads that regular file directly rather than following either link. Gemini aliases are recognized only when `GEMINI.md` is an effective Gemini context filename.
- `init-agents` and automatic fixes refuse symlinked `AGENTS.md` targets rather than writing through them.
- Existing regular `AGENTS.md` files are protected unless overwrite is explicit.
- A passing preflight is evidence about the checks performed, **not a security guarantee**.

See [SECURITY.md](SECURITY.md).

## Maintainer workflow

The project itself uses issue → branch → pull request → CI → merge → release.

Automated validation includes:

- Windows and Ubuntu;
- Python 3.10 and 3.13;
- built-wheel smoke tests;
- Action self-tests;
- strict self-audit;
- CodeQL;
- Dependabot;
- SARIF validation;
- PyPI publishing through GitHub OIDC Trusted Publishing.

## Install

PyPI:

```powershell
py -m pip install codex-workspace-bootstrap
```

Pinned GitHub release artifact:

```powershell
py -m pip install "https://github.com/kohli217/codex-workspace-bootstrap/releases/download/v1.0.0/codex_workspace_bootstrap-1.0.0-py3-none-any.whl"
```

## Development

```powershell
git clone https://github.com/kohli217/codex-workspace-bootstrap.git
cd codex-workspace-bootstrap
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e . pytest
pytest -q
```

Contributions and real-world usage reports are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md), [SUPPORT.md](SUPPORT.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and [docs/ADOPTION.md](docs/ADOPTION.md).

## License

MIT. See [LICENSE](LICENSE).
