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
.clinerules
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
