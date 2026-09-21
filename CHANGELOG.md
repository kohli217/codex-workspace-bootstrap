# Changelog

All notable changes to this project will be documented here.

## [Unreleased]

### Added
- CLI `--version` flag.
- Built-wheel smoke testing in CI.
- CodeQL static analysis.
- Dependabot updates for Python and GitHub Actions.
- Usage examples, citation metadata, Code of Conduct, and support guidance.

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
