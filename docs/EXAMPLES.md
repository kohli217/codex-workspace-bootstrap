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
Instruction integrity: 0 findings, 0 drift, 0 invalid commands
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

The generator uses observable repository evidence and separates unconfirmed validation commands for review.

## Detailed audit and CI gate

```powershell
cwb audit .
cwb audit . --strict
```

Tracked secret-risk filenames can become blocking. File contents are not printed by this check.

## JSON and SARIF

```powershell
cwb preflight . --json preflight.json
cwb audit . --sarif audit.sarif
```

## Doctor

```powershell
cwb doctor .
```

Doctor prints remediation guidance without installing software or changing system configuration.


## Cross-agent instruction lint

```powershell
cwb preflight . --fail-on-drift
```

The command exits non-zero when package-manager drift, validation-command drift, or invalid referenced package scripts are detected.

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
