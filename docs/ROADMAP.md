# Roadmap

This roadmap records intended work; it is not a promise of delivery dates.

## Current priorities

- reduce false positives in monorepos and repositories with nested/scoped agent instructions
- add regression fixtures from real public repositories without implying third-party adoption
- add more reproducible examples for mixed-tool and multi-agent repositories
- expand validation-command recognition where repository evidence can support it safely
- keep CLI, GitHub Action, release metadata, and documentation behavior aligned through regression tests
- keep the machine-readable preflight contract stable for external adapters
- continue supply-chain hardening without making solo-maintainer workflows impractical

## Recently completed

- one-command `preflight` with READY / NEEDS ATTENTION / BLOCKED states
- cross-agent instruction discovery for Codex/OpenAI agents, Copilot, Cline, Claude Code, Gemini CLI, Continue, and Cursor
- nested `AGENTS.md` / `AGENTS.override.md`, `CLAUDE.md`, Gemini CLI context files, and nested Cursor rule discovery
- scope-aware instruction integrity checks for package-manager drift, missing scripts, and validation-command conflicts
- safe fix preview with explicit `--apply`
- JSON, Markdown, and SARIF reporting
- versioned preflight report contract and shared policy evaluation for CLI, Action, and future adapters
- network-free GitHub Check adapter with schema validation and shared policy/result mapping
- constant-time GitHub webhook signature verification plus PR/push event normalization
- code-level minimum GitHub App permission/event contract plus a maintainer registration runbook
- repository-only preflight mode so remote App scans do not inherit the scanner host's toolchain state
- network-free GitHub App service core for signed webhook parsing, event routing, repository-only preflight, and Check rendering
- deterministic GitHub App JWT / installation-token / Check Run delivery request contract using the current REST API version
- hardened exact-revision Git checkout for push, pull request, and fork pull-request inspection without repository code execution
- dependency-free GitHub App worker runtime for RS256 signing, least-privilege token exchange, secure checkout, preflight, and Check Run publication
- reusable GitHub Action with Windows and Ubuntu self-tests, structured outputs, and an optional `require_ready` gate
- PyPI Trusted Publishing through GitHub OIDC
- CodeQL, Dependency Review, Dependabot, secret scanning, push protection, and protected `main`
- immutable SHA pinning for third-party GitHub Actions used by repository workflows
- hash-locked Python tooling for CI/release workflows
- signed GitHub release attestations with Sigstore bundle assets
- release/documentation consistency tests to prevent version drift
- package-manager-aware validation for npm, pnpm, Yarn, and Bun, including workspace/filter command forms
- Go, Rust, JVM, and .NET project-root detection without inventing unsupported validation commands
- broader dotenv risk detection for environment-specific files such as `.env.production`
- exact Release-to-PyPI artifact handoff so automatic publishing uses the same built distributions
- public regression coverage for real scoped-instruction patterns such as microsoft/vscode Copilot `applyTo` selectors

## Later

- richer Python, Node.js, and mixed-project evidence where it improves accuracy rather than adding heuristics
- additional repository-policy checks for maintainers
- safer generation of CI configuration from detected repository evidence
- broader SARIF interoperability and remediation metadata
- an HTTPS webhook ingress + durable queue/worker deployment that acknowledges GitHub within 10 seconds and invokes the existing worker runtime
- AI-agent skill adapters that run the same preflight contract before repository edits
- optional assisted instruction drafting, only when explicitly requested and never by sending repository content remotely by default

## Non-goals

- sending repository content to a remote service by default
- silently modifying project configuration
- auto-rewriting conflicting instruction files
- executing commands extracted from instruction files
- claiming that a passing audit proves a repository is secure
- claiming third-party adoption without a verifiable public reference
