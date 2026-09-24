# Changelog

All notable changes to this project will be documented here.

## [1.0.0] - 2026-09-23

### Stable contracts
- Declare the preflight report and root `.cwb.json` repository policy as explicit versioned machine-readable contracts, with JSON Schema available through `cwb schema preflight` and `cwb schema config`.
- Protect one shared repository-only preflight contract across the CLI, reusable GitHub Action, and GitHub App instead of allowing delivery surfaces to drift independently.
- Publish the v1.x semantic-versioning, deprecation, schema/config compatibility, and upgrade policy in `docs/STABILITY.md`.

### Agent and repository coverage
- Add conservative Windsurf `.windsurf/rules` discovery with always-on, glob, and model-decision trigger semantics.
- Back Windsurf handling with fixed public regression patterns modeled from C2FO/vfs, BetterRTX/BetterRTX-Installer, and dxos/dxos without claiming third-party adoption.
- Retain the broader v0.11 instruction-integrity baseline across Codex/OpenAI agents, GitHub Copilot, Cline, Claude Code, Gemini CLI, Continue, Cursor, and Windsurf.

### GitHub UX
- Explain `READY`, `NEEDS ATTENTION`, and `BLOCKED` directly near the top of the shared Markdown report used by CLI output, Action Job Summary, and GitHub App Check Runs.
- Keep the explicit security boundary that `READY` means current CWB checks passed; it is not a security guarantee.

### Release safety
- Promote package metadata from Alpha to Production/Stable for the 1.0 release candidate.
- Add an automatic CI guard that activates for package major version 1 or later and rejects incomplete release metadata, missing changelog/stability/schema documentation, or unexpected machine-contract version drift.
- Keep Windows and Ubuntu CI, Action smoke tests, build/container smoke tests, CodeQL, dependency review, and CWB self-preflight as release gates.

## [0.11.0] - 2026-09-23

### Added
- Public GitHub Marketplace preparation for the free CWB Preflight App, including secure Marketplace setup/OAuth verification and fail-closed plan lifecycle handling without widening repository permissions.
- File-level GitHub Check annotations for instruction-integrity findings and tracked secret-risk filenames, plus SARIF locations for structured audit paths.
- Optional root `.cwb.json` repository suppressions for narrowly scoped known false positives. Suppressions require reasons, remain visible in reports, and cannot hide blocking, essential-readiness, tracked secret-risk, or error-severity findings.
- Python validation-command recognition for Ruff, mypy, Pyright, tox, nox, and pre-commit, including safe normalization across direct, `python -m`, `uv run`, `poetry run`, and `pdm run` forms where applicable.

### Changed
- GitHub Check Runs now make applied repository suppressions and invalid suppression configuration visible directly on `.cwb.json`.
- Validation-command drift can now distinguish Python lint/typecheck/test/check families while preserving path-specific scope isolation.
- The public App remains public-repository-only on the zero-cost Cloudflare/GitHub Actions deployment and keeps the same least-privilege GitHub permissions.

### Safety
- Repository suppressions fail closed: only a regular non-symlink root `.cwb.json` up to 64 KB is accepted, exact relative paths are required for instruction suppressions, and unsafe broad suppressions are rejected.
- GitHub annotations continue to avoid reading or printing secret-file contents.
- Python validation recognition is lexical only; commands extracted from instructions are never executed.

### Documentation and regression coverage
- Added a CI-verified multi-agent Python demo showing real typecheck drift, wrapper equivalence, and isolation of path-specific Copilot rules.
- Added a fixed public regression fixture modeled from `plexe-ai/plexe` for Poetry-wrapped Pytest/Ruff guidance with a strict `CLAUDE.md -> AGENTS.md` compatibility alias.
- Expanded English/Japanese docs, GitHub App guidance, integration contracts, security notes, and roadmap coverage for the new behavior.

## [0.10.0] - 2026-09-22

### Fixed
- pnpm exact repository-relative path filters such as `pnpm --filter ./api test` now validate against the targeted package instead of dropping script validation.
- Package commands following a safe repository-relative `cd <dir> && ...` chain retain their lexical working-directory context for script validation without changing the public command-extraction API.
- npm `--prefix` and pnpm `--filter` routing are recognized when those options appear after the script name as well as before it, while script arguments after `--` remain untouched.
- Unfiltered pnpm `-r` / `--recursive` and npm `--workspaces` / `-ws` fan-out commands no longer produce root-package missing-script false positives.
- npm exact `--workspace` / `-w` selectors can resolve safe repository-relative workspace directories when the selector differs from the package name.

### Safety
- Exact path routing continues to reject absolute paths, parent traversal, glob/ambiguous selectors, unsafe cwd forms, and missing targets rather than guessing.
- Recursive/workspace fan-out handling deliberately avoids emulating complete package-manager selection semantics; commands extracted from instructions remain non-executable lint evidence only.

### Documentation
- Added fixed public regression fixtures for `unraid/api`, `bytedance/deer-flow`, `withcoral/coral`, `marktoflow/marktoflow`, `forwardsoftware/react-auth`, `KutyAI/Private-Hosting-App`, and `kryten87/PromptKitchen`.

## [0.9.0] - 2026-09-22

### Added
- Real-world regression fixtures for targeted-workspace, targeted-directory, inline-option, and shared multi-agent instruction layouts observed in d3plus/d3plus, TracecatHQ/tracecat, broadinstitute/warp, WordPress/pattern-directory, vtex/address-form, and kickflip-labs/cissp-study-hub.
- Safe canonical-instruction aliases for Claude Code and Gemini CLI when an exact sibling `CLAUDE.md -> AGENTS.md` or `GEMINI.md -> AGENTS.md` link targets a regular `AGENTS.md`; Gemini aliases continue to honor project `context.fileName` settings.

### Fixed
- Monorepo package-script validation now resolves exact pnpm filters, npm workspace selectors, and Yarn workspace targets instead of incorrectly validating workspace-only scripts against the root package.
- Directory-targeted commands now validate scripts against the explicitly selected package for pnpm `-C` / `--dir`, npm `--prefix`, and Yarn/Bun `--cwd`, while unsafe or ambiguous directory targets do not fall back to unrelated root scripts.
- Yarn command extraction preserves inline options such as `yarn --cwd=website build`.
- npm workspace selectors placed after `run <script>` are resolved in `--workspace` / `-w` forms up to npm's `--` script-argument separator.

### Security
- Safe Claude/Gemini aliases are recognized from lexical link metadata only; CWB revalidates the alias and reads the regular sibling `AGENTS.md` directly rather than trusting instruction content through a symbolic link.
- Absolute/other alias targets, parent traversal, missing targets, and chained/symlinked `AGENTS.md` targets remain rejected, and write operations continue to refuse symlinked `AGENTS.md` targets.

### Documentation
- Expanded the reproducible public-repository evaluation set to document the exact monorepo and shared-instruction patterns protected by v0.9.0.

## [0.8.0] - 2026-09-22

### Added
- A complete GitHub App integration contract: Check rendering, constant-time signed-webhook verification, push/pull-request normalization, repository-only preflight, and a network-free service core.
- Deterministic GitHub App JWT, installation-token, and Check Run delivery contracts plus hardened exact-revision checkout for pushes, pull requests, and fork pull requests without executing repository code.
- A least-privilege GitHub App worker runtime with repository-scoped installation tokens and completed-delivery idempotency using GitHub delivery IDs and Check Run `external_id`.
- GitHub App Manifest registration plus a Cloud Run + Pub/Sub reference deployment with separated ingress/worker identities and durable redelivery.
- A completely free Cloudflare Worker + Queue + public GitHub Actions deployment using GitHub Actions OIDC for installation-token brokering, with private-repository events rejected before queueing.
- A reproducible scoped-monorepo demo and an additional fixed public-repository Gemini CLI `context.fileName` regression fixture.

### Fixed
- GitHub REST requests now include the required User-Agent.
- The Windows Cloudflare deploy isolates a verified Node.js 22/Wrangler toolchain from machine-wide Node, handles harmless PowerShell native stderr correctly, reuses interrupted KV/Queue/secret state, and guides current workers.dev onboarding.
- The free deployment reuses the persisted GitHub dispatch credential and no longer depends on repository Actions Variables permissions.
- GitHub App Manifest callbacks use signed stateless state, recover safely from async callback failures, and reuse already-stored credentials instead of duplicating Apps.
- The live GitHub App Actions worker exposes the src-layout package correctly and authenticates exact Git fetches with GitHub's installation-token HTTP Basic contract.

### Security
- GitHub App setup bootstrap tokens expire after one hour; Manifest callback state is HMAC-signed and time-limited.
- App permissions remain least-privilege: Checks read/write, Contents read-only, and Pull requests read-only; runtime installation tokens are narrowed further to the single event repository with only `contents:read` and `checks:write`.
- The free public-OSS path rejects private-repository webhook events before they reach the public Actions worker.
- Checkout disables interactive credentials, system/global Git config, hooks, submodules, and repository command execution.

### Documentation
- The GitHub App is documented as a shipped integration, including the zero-cost public-repository deployment, live installed-App E2E milestone, and a promotion runbook for reusing the verified development App as a public App.
- Added a real-world scoped monorepo example covering nearest package-manager evidence.

## [0.7.0] - 2026-09-22

### Added
- `--require-ready` CLI policy and `require_ready` GitHub Action input for CI that must reject both NEEDS ATTENTION and BLOCKED states.
- Project-signal detection for Go, Rust, JVM, and .NET repositories without inventing unsupported validation commands.
- A public microsoft/vscode regression fixture for brace-wrapped Copilot `applyTo` selectors.

### Fixed
- Brace-wrapped scoped instruction selectors now keep their correct static scope, while embedded brace expansions remain intact.
- Root package-manager evidence conflicts are no longer duplicated between repository-audit and instruction-integrity output.
- The PowerShell installer now stays version-locked to package metadata through regression coverage.
- Git tracked-file enumeration now handles undecodable filename bytes without text-mode Unicode failures.

### Security
- Environment-specific dotenv files such as `.env.production` and `.env.development.local` are detected while common template names remain excluded.
- Tracked secret-risk filenames remain visible even inside filesystem-pruned directories such as `node_modules`, `dist`, and `build`.
- Automatic PyPI publishing now uses the exact wheel and source distribution produced by the triggering Release workflow rather than rebuilding or selecting the latest release.

### Maintenance
- Release distributions are validated before attestation and preserved as short-lived workflow artifacts for exact PyPI handoff.
- Release permission and publishing documentation now matches the implemented OIDC/attestation workflow.

## [0.6.1] - 2026-09-21

### Fixed
- Audit and preflight now use repository package-manager evidence instead of assuming npm for Node.js projects.
- Conflicting package-manager evidence is surfaced directly by the repository audit and prioritized in next actions.
- Workspace/filter commands such as `pnpm --filter`, `pnpm -C`, `npm --workspace`, and `yarn workspace` are parsed through to the real script name for validation.
- Secret-risk traversal now prunes generated directories before walking them and no longer misbehaves when the repository itself lives under a parent directory named `build`.
- Doctor and SARIF remediation guidance now covers npm, pnpm, Yarn, Bun, and package-manager evidence conflicts.

### Security
- README, license, ignore files, AGENTS.md, project manifests, and pytest marker files are no longer trusted through symbolic links.
- Project detection and generated AGENTS.md validation planning now ignore symlinked project markers.

### Maintenance
- Updated artifact upload/download and CodeQL SARIF upload Actions to current SHA-pinned releases.

## [0.6.0] - 2026-09-21

### Added
- Scope-aware discovery for nested `CLAUDE.md` and hierarchical Gemini CLI context files.
- Support for Gemini CLI project `context.fileName` overrides, including multiple configured filenames.
- Structured GitHub Action outputs for readiness state, instruction findings, blocking findings, and warnings.
- Multiline frontmatter list parsing for scoped instruction globs.
- End-to-end Action regression coverage for integrity-gate failures.

### Changed
- Instruction discovery now prunes generated/dependency directories during filesystem traversal.
- Chained shell validation commands are split before linting so each command can be checked independently.
- Workspace/filter package-manager flags are handled conservatively to avoid false missing-script findings.
- `init-agents` now derives Node.js validation commands from package-manager evidence instead of defaulting to npm.
- The reusable GitHub Action performs one preflight pass for reporting and gating.
- Release metadata and copy-pasteable Action documentation are protected by consistency regression tests.

### Security
- Repository instruction/configuration inputs are not read through symbolic links.
- `init-agents` and automatic fixes refuse symlinked `AGENTS.md` write targets.

## [0.5.2] - 2026-09-21

### Fixed
- Align the CLI-reported version with package metadata.
- Use OS-specific hash-locked Python tool dependencies in CI.

### Security
- Attach the Sigstore attestation bundle to GitHub Release assets for external verification and OpenSSF detection.
- Hash-pin Python workflow tooling across CI, CodeQL, release, and PyPI publication.

## [0.5.1] - 2026-09-21

### Added
- GitHub private vulnerability reporting guidance and a private security-report contact link.
- Dependency Review for pull requests, enforced as a required status check.
- Signed GitHub Artifact Attestations for future release distributions.

### Changed
- Protected the default branch with required pull requests, required CI checks, deletion protection, and force-push blocking.
- Pinned GitHub Actions dependencies to immutable commit SHAs.
- Scoped GitHub Actions write permissions to the jobs that require them.
- Enabled dependency graph, Dependabot security updates, grouped security updates, secret protection, and push protection.

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
