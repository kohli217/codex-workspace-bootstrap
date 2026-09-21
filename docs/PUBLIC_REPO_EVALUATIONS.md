# Public repository evaluations

These are **read-only technical evaluations of public repository snapshots** used to validate detector coverage and false-positive resistance.

They are **not** claims that the listed projects use, endorse, or have installed `codex-workspace-bootstrap`.

## Method

For each repository, the evaluation records a specific public commit and inspects only repository-visible instruction/configuration signals and package-manager evidence relevant to the deterministic preflight.

No repository contents were modified.

## openai/codex

Snapshot: `a6fdb11eda992b706c5e6a21ae5fd8c7376f8e06`

Observed signals:

- root `AGENTS.md`;
- root `package.json`;
- root `pnpm-lock.yaml`;
- `package.json` declares `packageManager: pnpm@...`.

Why this matters:

- exercises Codex/OpenAI-agent instruction discovery;
- provides strong repository evidence for the JavaScript package manager;
- demonstrates why package-manager comparison should use package metadata/lockfiles rather than infer from prose.

Expected behavior of the v0.5 integrity model:

- detect `AGENTS.md`;
- select pnpm as repository package-manager evidence;
- flag a mismatch only if executable-looking AI instructions explicitly prescribe a different JavaScript package manager.

## Cline/Cline

Snapshot: `ee46dc4bd72bf7c7cc2bf554f43dd5b728fa72db`

Observed signals:

- root `AGENTS.md`;
- `.github/copilot-instructions.md`;
- a populated `.clinerules/` tree;
- root `package.json`;
- `package.json` declares `packageManager: bun@1.3.13`.

Both sampled instruction sources use Bun commands.

Why this matters:

- this is a real multi-instruction repository;
- it exercises cross-agent coverage across AGENTS, Copilot instructions, and Cline rules;
- it is a useful false-positive test: different files can contain different *additional* commands while sharing a compatible validation baseline.

Expected behavior of the v0.5 integrity model:

- detect multiple instruction sources;
- recognize Bun as repository package-manager evidence;
- avoid package-manager mismatch findings for Bun commands;
- avoid treating every difference in command lists as drift merely because one file documents additional commands.

## continuedev/continue

Snapshot: `5522c6f44ca0ac3528b37244818fbfa39b5af470`

Observed signals:

- a populated `.continue/rules/` tree;
- root `package.json`;
- root `package-lock.json`;
- sampled Continue rule documents a Gradle test command for the IntelliJ subproject.

Why this matters:

- exercises directory-based Continue rule discovery;
- demonstrates a mixed repository where an instruction can legitimately describe a non-JavaScript subproject even when npm evidence exists at the root;
- validates the decision not to infer a JavaScript package-manager conflict from unrelated Gradle commands.

Expected behavior of the v0.5 integrity model:

- detect Continue rules;
- retain npm as root JavaScript package-manager evidence;
- not flag Gradle commands as npm drift.

## What these evaluations do not prove

These evaluations do not prove:

- that every instruction in these repositories is semantically correct;
- that the projects use this tool;
- that the current heuristics cover every agent or monorepo layout;
- that a clean preflight is a security guarantee.

They provide reproducible, real-world fixtures for the product model and document the boundary between useful deterministic checks and claims that require human review.

## Regression policy

When instruction parsing or drift rules change, maintainers should re-check these repository patterns before release:

1. single primary instruction file + explicit package manager;
2. multiple agent-specific instruction sources sharing a common toolchain;
3. mixed-language/subproject rules where unrelated commands must not trigger JavaScript drift.


## Regression fixtures

The observed repository patterns are encoded as automated regression tests in `tests/test_public_repo_patterns.py`:

- `test_public_pattern_openai_codex_pnpm_repo_without_js_command_drift`
- `test_public_pattern_cline_multi_instruction_bun_baseline_is_compatible`
- `test_public_pattern_continue_gradle_rule_does_not_conflict_with_root_npm`

The fixtures intentionally model only the relevant public signals needed to exercise the lint rules. They are not copies of the upstream repositories and they do not imply compatibility certification.
