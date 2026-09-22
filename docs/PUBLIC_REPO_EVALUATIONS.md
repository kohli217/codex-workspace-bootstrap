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

## microsoft/vscode

Snapshot: `b761e4ed5a30fd66137ea5fab7f3b36d341b5d24`

Observed signals:

- root `AGENTS.md`;
- a large `.github/instructions/*.instructions.md` tree;
- path-specific Copilot frontmatter using `applyTo`;
- `.github/instructions/writing-tests.instructions.md` uses a brace-wrapped selector:
  `{src/vs/**/test/**,src/vs/**/*.test.ts,src/vs/**/*.integrationTest.ts}`;
- nested `AGENTS.md` files under source subtrees.

Why this matters:

- exercises a real path-specific Copilot layout from a large monorepo;
- demonstrates that comma-separated alternatives inside an outer brace selector are one scoped selector, not unrelated root-level fragments;
- protects static scope inference from collapsing `src/vs` to repository root.

Expected behavior of the current integrity model:

- detect the Copilot instruction file as path-specific;
- infer static scope `src/vs` for the brace-wrapped selector;
- keep embedded brace expansion such as `apps/web/{src,tests}/**` scoped to `apps/web`;
- avoid promoting the path-specific rule to a repository-wide baseline.

## ModelEngine-Group/fit-framework

Snapshot: `e2f285d1cf2f4d53330b2796bc56ecce6dc63544`

Observed signals:

- root `AGENTS.md`;
- project `.gemini/settings.json`;
- Gemini CLI `context.fileName` is configured as `["AGENTS.md"]`.

Why this matters:

- exercises a real repository that intentionally reuses the vendor-neutral `AGENTS.md` file as Gemini CLI context;
- verifies that CWB honors the project-level Gemini filename override instead of requiring a separate `GEMINI.md`;
- protects multi-agent discovery so one physical instruction file can be recognized by both Codex/OpenAI agents and Gemini CLI without being duplicated.

Expected behavior of the current integrity model:

- detect root `AGENTS.md` for Codex/OpenAI agents;
- also detect that same `AGENTS.md` as Gemini CLI context because of `.gemini/settings.json`;
- not invent a `GEMINI.md` signal when that filename is not part of the configured context list.

## d3plus/d3plus

Snapshot: `2818442024fe3d2d3e25476dd69fe2c9337780fb`

Observed signals:

- root `AGENTS.md`;
- root `package.json` selects pnpm;
- root package does not define a `dev` script;
- `packages/core/package.json` is named `@d3plus/core` and does define `dev`;
- root instructions use `pnpm --filter @d3plus/core run dev`.

Why this matters:

- exercises a real monorepo command whose script belongs to a targeted workspace rather than the root package;
- prevents CWB from reporting a false `missing-package-script` finding merely because the root package lacks the workspace's script;
- validates exact workspace-name resolution without executing repository code.

Expected behavior of the current integrity model:

- recognize pnpm from root repository evidence;
- resolve the exact `@d3plus/core` workspace target;
- validate `dev` against that workspace package;
- avoid a missing-script warning when the targeted workspace defines the script;
- still report a missing script when an exact resolved workspace truly lacks it.

## TracecatHQ/tracecat

Snapshot: `45eb759264c4897dda6cfc2ccc3afe58d5985482`

Observed signals:

- root `AGENTS.md`;
- no root `package.json` at this snapshot;
- `frontend/package.json` selects pnpm and defines `test`;
- root instructions use `pnpm -C frontend test`.

Why this matters:

- exercises a real repository-level instruction that targets a package by repository-relative directory;
- verifies that script validation follows the explicit pnpm working directory rather than unrelated root package evidence;
- protects directory-targeted validation without executing repository commands or reading outside the repository.

Expected behavior of the current integrity model:

- parse `-C frontend` as a repository-relative directory target;
- validate `test` against `frontend/package.json`;
- reject absolute paths and `..` traversal from evidence resolution;
- avoid a false missing-script finding when the targeted package defines the script;
- still report a missing script when the targeted package exists but lacks it.

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
- `test_public_pattern_vscode_brace_wrapped_apply_to_keeps_static_scope`
- `test_public_pattern_fit_framework_gemini_reads_agents_md`
- `test_public_pattern_d3plus_workspace_filter_uses_workspace_script`

The fixtures intentionally model only the relevant public signals needed to exercise the lint rules. They are not copies of the upstream repositories and they do not imply compatibility certification.
