# Roadmap

This roadmap records intended work; it is not a promise of delivery dates.

## Current priorities

- reduce false positives in monorepos and repositories with nested/scoped agent instructions
- add regression fixtures from real public repositories without implying third-party adoption
- add more reproducible examples for mixed-tool and multi-agent repositories
- expand validation-command recognition where repository evidence can support it safely
- keep CLI, GitHub Action, release metadata, and documentation behavior aligned through regression tests
- continue supply-chain hardening without making solo-maintainer workflows impractical

## Recently completed

- one-command `preflight` with READY / NEEDS ATTENTION / BLOCKED states
- cross-agent instruction discovery for Codex/OpenAI agents, Copilot, Cline, Claude Code, Gemini CLI, Continue, and Cursor
- nested `AGENTS.md` / `AGENTS.override.md` and nested Cursor rule discovery
- scope-aware instruction integrity checks for package-manager drift, missing scripts, and validation-command conflicts
- safe fix preview with explicit `--apply`
- JSON, Markdown, and SARIF reporting
- reusable GitHub Action with Windows and Ubuntu self-tests
- PyPI Trusted Publishing through GitHub OIDC
- CodeQL, Dependency Review, Dependabot, secret scanning, push protection, and protected `main`
- immutable SHA pinning for third-party GitHub Actions used by repository workflows
- hash-locked Python tooling for CI/release workflows
- signed GitHub release attestations with Sigstore bundle assets
- release/documentation consistency tests to prevent version drift

## Later

- richer Python, Node.js, and mixed-project evidence where it improves accuracy rather than adding heuristics
- additional repository-policy checks for maintainers
- safer generation of CI configuration from detected repository evidence
- broader SARIF interoperability and remediation metadata
- optional assisted instruction drafting, only when explicitly requested and never by sending repository content remotely by default

## Non-goals

- sending repository content to a remote service by default
- silently modifying project configuration
- auto-rewriting conflicting instruction files
- executing commands extracted from instruction files
- claiming that a passing audit proves a repository is secure
- claiming third-party adoption without a verifiable public reference
