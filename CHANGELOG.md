# Changelog

All notable changes to this project will be documented here.

## [0.5.0] - 2026-09-21

### Added
- Cross-agent instruction integrity lint across supported AI coding instruction formats.
- Repository-evidence validation using packageManager, lockfiles, and package.json scripts.
- Detection for package-manager mismatch/drift, invalid referenced scripts, and conflicting validation commands.
- `cwb fix .` safe preview with explicit `--apply` for low-risk supported fixes only.
- `--fail-on-integrity` CLI policy and `fail_on_integrity` GitHub Action input.
- Instruction integrity metrics in CLI, JSON, Markdown, and GitHub Actions Job Summary.
- Reproducible read-only evaluations of public repositories.
- Scope-aware discovery for nested `AGENTS.md` / `AGENTS.override.md`.
- Nested Cursor `.cursor/rules/*.mdc` discovery with conservative `globs` / `alwaysApply` applicability semantics.
- Static scope inference from common `applyTo` and `globs` frontmatter.
- Validation-command recognition for uv/poetry/pdm pytest flows, make/just, Gradle, Maven, and dotnet.
- Comprehensive preflight SARIF containing repository-audit and instruction-integrity findings with file locations.

### Changed
- Readiness becomes NEEDS ATTENTION when instruction-integrity findings exist.
- Validation drift comparison now uses command families, shared baselines, and instruction scopes to reduce false positives.
- Path-specific rules are validated individually but excluded from coarse cross-file drift comparison when full selector semantics are unavailable.
- READY now requires a repository-wide instruction baseline, not only nested/path-specific rules.
- Integrity gate terminology now reflects all integrity findings rather than only drift.

## [0.4.0] - 2026-09-21

### Added
- One-command `preflight` experience with READY / NEEDS ATTENTION / BLOCKED states.
- Short `cwb` CLI alias.
- Cross-agent instruction/config detection for Codex/OpenAI agents, GitHub Copilot, Cline, Claude Code, Gemini CLI, Continue, and Cursor.
- Prioritized P0/P1/P2 next actions.
- Markdown preflight reports for pull requests, issues, and CI summaries.
- GitHub Actions Job Summary integration.

- PyPI Trusted Publishing workflow using GitHub OIDC, with tag/version verification and distribution validation.
- v0.3.0 published to PyPI through the Trusted Publishing workflow.
- Windows-focused `doctor` command with non-destructive remediation guidance.

### Changed
- README and onboarding repositioned around AI coding repository preflight.
- AGENTS.md generation now validates suggested commands against project metadata, package scripts, pytest configuration, and README evidence.
- Plausible but unconfirmed test commands are separated as review-required suggestions instead of being treated as authoritative.

## [0.3.0] - 2026-09-21

### Added
- SARIF 2.1.0 output for repository-readiness warnings and blocking findings.
- GitHub Code Scanning integration documentation.
- Reusable Action SARIF output with validated inputs.
- CODEOWNERS and GitHub Marketplace publishing documentation.

## [0.2.0] - 2026-09-21

### Added
- CLI `--version` flag.
- Built-wheel smoke testing in CI.
- CodeQL static analysis.
- Dependabot updates for Python and GitHub Actions.
- Usage examples, citation metadata, Code of Conduct, and support guidance.
- Reusable GitHub Action integration with Windows and Ubuntu self-tests.
- Ecosystem motivation, maintainer identity, and usage-reporting documentation.

### Changed
- README onboarding now recommends a pinned release artifact instead of piping a remote PowerShell script directly into `iex`.
- Package metadata now includes project URLs and broader discovery keywords.

## [0.1.0] - 2026-09-21

### Added
- Windows-focused repository and developer-tool audit.
- Detection for README, license, .gitignore, AGENTS.md, and common manifests.
- Checks for Git, Python, Node.js, npm, PowerShell, WSL, and Codex.
- Filename-based warnings for common secret-bearing files.
- JSON report output.
- Project-aware `AGENTS.md` bootstrap for Python, Node.js, mixed, and unknown repositories.
- Initial test suite and GitHub Actions CI.
