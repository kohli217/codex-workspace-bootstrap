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

## broadinstitute/warp

Snapshot: `8005650febe5d452ba8fbe48c40f14c953bccbcb`

Observed signals:

- root `AGENTS.md`;
- no root `package.json` at this snapshot;
- `website/package.json` defines `start` and `build`;
- root instructions use inline Yarn cwd forms such as `yarn --cwd=website start` and `yarn --cwd=website build`.

Why this matters:

- exercises a real inline long-option form where the directory target is attached with `=`;
- protects command extraction from truncating `--cwd=website` before script validation;
- verifies that the already-safe directory-target resolver receives the full command and checks the targeted package.

Expected behavior of the current integrity model:

- extract the full Yarn command including the inline cwd value;
- resolve `website` as a safe repository-relative directory target;
- validate `start` / `build` against `website/package.json`;
- avoid a false missing-script finding when the targeted package defines the script;
- still report a missing script when the targeted package exists but lacks it.

## WordPress/pattern-directory

Snapshot: `4482f3863de14e1dbdfd8e290bd027ba322f8e79`

Observed signals:

- root `AGENTS.md`;
- root `package.json` uses npm workspaces and does not define `test:unit`;
- `public_html/wp-content/plugins/pattern-creator/package.json` is named `wporg-pattern-creator` and defines `test:unit`;
- root instructions use `npm run test:unit --workspace=wporg-pattern-creator`.

Why this matters:

- exercises npm's common syntax where the workspace selector follows `run <script>`;
- prevents CWB from validating a workspace-only script against the root package;
- verifies that npm options after the script are parsed only until the `--` script-argument separator.

Expected behavior of the current integrity model:

- resolve an exact post-script `--workspace` / `-w` selector;
- validate `test:unit` against the named workspace package;
- avoid a false missing-script warning when the workspace defines the script;
- preserve a true warning when the resolved workspace lacks the script;
- treat workspace-looking text after npm's `--` separator as script arguments, not npm routing options.

## vtex/address-form

Snapshot: `2643de390eaaff7e2bfc288b9a2841033e77932c`

Observed signals:

- root `AGENTS.md` is a regular file;
- root `CLAUDE.md` is a Git symlink (mode `120000`);
- the symlink blob contains exactly `AGENTS.md`;
- the repository documents the link as the Claude Code compatibility entry point.

Why this matters:

- exercises a common multi-agent layout that intentionally keeps one canonical instruction file;
- lets CWB report Claude Code coverage without trusting instruction content through an arbitrary symbolic link;
- preserves the security boundary by accepting only an exact sibling alias to a regular `AGENTS.md`.

Expected behavior of the current integrity model:

- detect regular `AGENTS.md` for Codex/OpenAI agents;
- recognize exact `CLAUDE.md -> AGENTS.md` (or `./AGENTS.md`) as a Claude Code alias;
- read the regular `AGENTS.md` directly when linting the alias;
- reject parent traversal, absolute/other targets, missing targets, and symlinked/chained `AGENTS.md` targets;
- continue ignoring all other symlinked instruction/configuration inputs.

## kickflip-labs/cissp-study-hub

Snapshot: `1f92eb8a507380fcda577263e2213e1f8d0a4b27`

Observed signals:

- root `AGENTS.md` is a regular file;
- root `CLAUDE.md` and `GEMINI.md` are Git symlinks (mode `120000`);
- both symlink blobs contain exactly `AGENTS.md`;
- the repository documents both aliases as tool compatibility entry points.

Why this matters:

- exercises a real three-agent layout with one canonical instruction file;
- verifies that the same strict lexical alias boundary can serve both Claude Code and Gemini CLI;
- protects Gemini project configuration: a `GEMINI.md` alias is only active when that filename is part of the effective Gemini context list.

Expected behavior of the current integrity model:

- detect `AGENTS.md` for Codex/OpenAI agents;
- recognize exact sibling `CLAUDE.md -> AGENTS.md` for Claude Code;
- recognize exact sibling `GEMINI.md -> AGENTS.md` for Gemini CLI when `GEMINI.md` is effective context;
- read only the regular `AGENTS.md` directly for alias linting;
- ignore a `GEMINI.md` alias when project settings replace Gemini's context filename list.

## unraid/api

Snapshot: `d0615255e0ce062f7a8262e560f963d07f311539`

Observed signals:

- root `AGENTS.md`;
- root package selects pnpm;
- `pnpm-workspace.yaml` includes `./api`;
- `api/package.json` is named `@unraid/api` and defines `test`;
- root instructions use `pnpm --filter ./api test`.

Why this matters:

- exercises pnpm's exact repository-relative path selector rather than a package-name selector;
- prevents CWB from dropping script validation merely because `./api` does not equal the package name `@unraid/api`;
- keeps complex pnpm filter syntax unresolved unless it can be mapped deterministically and safely.

Expected behavior of the current integrity model:

- recognize an exact `./relative/path` pnpm filter as a repository-relative package target;
- validate the script against that target's regular `package.json`;
- reject parent traversal and leave glob/dependency/negated selectors unresolved;
- preserve a missing-script warning when the exact path target exists but lacks the referenced script.

## bytedance/deer-flow

Snapshot: `53352287a7197cc609379536e9d2ee5580740add`

Observed signals:

- root `AGENTS.md`;
- no root `package.json` at this snapshot;
- `frontend/package.json` selects pnpm and defines `check` and `test`;
- root instructions use `cd frontend && pnpm check` and `cd frontend && pnpm test`.

Why this matters:

- exercises a common shell form where package validation runs after an explicit directory change;
- protects CWB from discarding the cwd context and validating against unrelated root evidence;
- keeps public `extract_commands()` output stable while allowing linting to retain additional lexical command context internally.

Expected behavior of the current integrity model:

- preserve a safe exact repository-relative `cd` target across `&&` command segments;
- validate plain package scripts against that directory's regular `package.json`;
- support quoted relative directory names;
- leave traversal, expansion, glob, absolute, and nested-routing forms unresolved rather than guessing;
- continue returning the bare package command from `extract_commands()`.

## withcoral/coral

Snapshot: `2c58881841bf62fc52a44bb5c2571760e65a58dd`

Observed signals:

- root `AGENTS.md`;
- no root `package.json` at this snapshot;
- `apps/coral-ui/package.json` defines `test`, `build`, `check`, `typecheck`, and `test:server`;
- root instructions use post-script npm directory routing such as `npm test --prefix apps/coral-ui` and `npm run build --prefix apps/coral-ui`.

Why this matters:

- exercises npm's valid global `--prefix` option when it appears after the command/script name;
- prevents CWB from dropping package-script validation merely because the directory option is post-script;
- distinguishes npm routing options from script arguments after npm's `--` separator.

Expected behavior of the current integrity model:

- resolve exactly one `--prefix <dir>` or `--prefix=<dir>` before npm's `--` separator;
- validate the referenced script against that target's regular `package.json`;
- preserve existing pre-script `--prefix` behavior;
- leave repeated, missing, or unsafe prefix targets unresolved;
- treat `--prefix` after npm's `--` separator as a script argument rather than directory routing.

## marktoflow/marktoflow

Snapshot: `707a57c9aa4f5af389cc873f5a4d9a2983d1f7fb`

Observed signals:

- root `AGENTS.md`;
- root `package.json` selects pnpm and defines a root `test` script;
- `packages/core/package.json` is named `@marktoflow/core` and defines `test`;
- `packages/integrations/package.json` is named `@marktoflow/integrations` and defines `test`;
- root instructions use post-script filters such as `pnpm test --filter=@marktoflow/core`.

Why this matters:

- exercises pnpm filtering when `--filter` appears after the script command;
- prevents CWB from silently validating a workspace-targeted command against the root script set;
- protects both exact package-name and exact `./path` target resolution while leaving complex selectors unresolved.

Expected behavior of the current integrity model:

- resolve exactly one `--filter <target>`, `-F <target>`, `--filter=<target>`, or `-F=<target>` before pnpm's `--` separator;
- validate exact package-name targets against that workspace's regular `package.json`;
- reuse safe exact-path handling for `./relative/path` selectors;
- preserve a true missing-script warning when the selected workspace lacks the script even if root defines it;
- leave repeated or complex selectors unresolved rather than guessing.

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
- `test_public_pattern_tracecat_directory_target_uses_frontend_package`
- `test_public_pattern_warp_yarn_inline_cwd_uses_website_package`
- `test_public_pattern_wordpress_npm_post_script_workspace_uses_workspace_script`
- `test_public_pattern_vtex_claude_alias_reuses_regular_agents`
- `test_public_pattern_cissp_shared_claude_and_gemini_aliases`
- `test_public_pattern_unraid_pnpm_exact_path_filter_uses_api_package`
- `test_public_pattern_deer_flow_cd_frontend_uses_frontend_package`
- `test_public_pattern_coral_npm_post_script_prefix_uses_coral_ui`
- `test_public_pattern_marktoflow_pnpm_post_script_filter_uses_workspace`

The fixtures intentionally model only the relevant public signals needed to exercise the lint rules. They are not copies of the upstream repositories and they do not imply compatibility certification.
