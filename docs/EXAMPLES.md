# Examples

## One-command AI repository preflight

```powershell
py -m pip install codex-workspace-bootstrap
cwb preflight .
```

Typical output:

```text
AI Repository Preflight
Repository: C:\work\my-project
State: NEEDS ATTENTION
Project: Python
AI instructions: none detected
Audit: 10 passed, 4 warnings, 0 blocking
Instruction integrity: 0 findings, 0 drift, 0 invalid commands, 0 metadata
Next actions:
  [P1] Add repository instructions for AI coding agents -> cwb init-agents .
```

## Generate a reviewable Markdown report

```powershell
cwb preflight . --markdown preflight.md
```

Use the report in a pull request, issue, or maintainer review.

## Detect existing AI instruction coverage

The preflight detects known repository instruction/config signals such as:

```text
AGENTS.md
.github/copilot-instructions.md
.github/instructions/*
.clinerules/*
.cline/rules/*
CLAUDE.md
GEMINI.md
.continue/rules/*
.cursorrules
.cursor/rules/*
```

Detection means "present", not "correct"; maintainers should still review the files.

## Generate project-aware AGENTS.md

```powershell
cwb init-agents .
```

The generator recognizes common Python, Node.js, Go, Rust, JVM, and .NET project roots. It only emits validation commands when repository evidence supports them, and separates unconfirmed suggestions for review.

## Detailed audit and CI gates

```powershell
cwb audit .
cwb audit . --strict
```

Tracked secret-risk filenames can become blocking. Environment-specific dotenv files such as `.env.production` are included, while common templates such as `.env.example` are excluded. File contents are not printed by this check.

Require the complete preflight state to be `READY`:

```powershell
cwb preflight . --require-ready
```

Use this when CI should also fail for readiness gaps that are not blocking security findings, such as missing repository-wide AI instructions or essential repository markers.

## JSON and SARIF

```powershell
cwb preflight . --json preflight.json
cwb preflight . --sarif preflight.sarif
```

## Doctor

```powershell
cwb doctor .
```

Doctor prints remediation guidance without installing software or changing system configuration.


## Cross-agent instruction lint

```powershell
cwb preflight . --fail-on-integrity
```

The command exits non-zero when any instruction-integrity finding is detected, including drift, invalid referenced package scripts, conflicting package-manager evidence, or missing scope metadata.

## Safe fix preview

```powershell
cwb fix .
```

Review the plan first. Apply only supported low-risk changes with:

```powershell
cwb fix . --apply
```

Conflicting existing instruction files are never auto-rewritten.


## Nested and path-specific instructions

`cwb` detects nested Codex instructions such as:

```text
AGENTS.md
services/payments/AGENTS.override.md
```

It also reads common frontmatter scopes such as:

```yaml
---
applyTo: "services/api/**/*.py"
---
```

and:

```yaml
---
globs: extensions/intellij/**/*Test.kt
---
```

The inferred scope is shown in CLI and Markdown output. Different scopes are not compared as if they were repository-wide rules.


### Conservative path-specific comparison

Path-specific rules are still checked against nearby repository evidence such as `packageManager`, lockfiles, and `package.json` scripts. They are not cross-compared with repository-wide or other path-specific rules when only a coarse static prefix is known. This avoids false drift findings between selectors such as `**/*.py` and `**/*.ts`.


## Nested Cursor rules

Cursor project rules can be discovered below subdirectories:

```text
backend/server/.cursor/rules/always.mdc
frontend/.cursor/rules/react.mdc
```

A rule with `alwaysApply: true` is treated as a baseline for its containing directory scope. A rule with globs is path-specific. A rule that is neither always-on nor glob-scoped is reported as conditional and does not count as a repository-wide readiness baseline.


## Package-manager-aware validation

For Node.js repositories, `cwb` uses repository evidence such as `packageManager` and lockfiles instead of assuming npm.

Examples it can validate include:

```text
pnpm --filter web run lint
pnpm -C apps/web test
npm --workspace app run lint
yarn workspace web test
```

Conflicting package-manager evidence is surfaced for review instead of silently choosing one manager.

## Hierarchical AI instructions

The preflight understands nested instruction layouts such as:

```text
CLAUDE.md
services/api/CLAUDE.md
GEMINI.md
apps/web/GEMINI.md
```

Gemini CLI project `.gemini/settings.json` `context.fileName` overrides are also respected when present.
