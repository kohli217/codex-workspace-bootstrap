from pathlib import Path
import json

from codex_workspace_bootstrap.fixes import apply_fix_plan, build_fix_plan
from codex_workspace_bootstrap.instructions import (
    detect_instruction_signals,
    extract_commands,
    finding_summary,
    lint_instructions,
)


def test_extract_commands_prefers_executable_regions() -> None:
    text = """
Use npm in this repository.

Run:
§§§bash
pnpm test
pnpm run lint
§§§

You can also use §python -m pytest§ for the Python package.
""".replace("§", "`")

    commands = extract_commands(text)

    assert "pnpm test" in commands
    assert "pnpm run lint" in commands
    assert "python -m pytest" in commands
    assert "npm" not in commands


def test_package_manager_mismatch_uses_repo_evidence(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@9.0.0",
                "scripts": {"test": "vitest", "lint": "eslint ."},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Run §npm test§.\n".replace("§", "`"), encoding="utf-8")

    findings = lint_instructions(tmp_path)

    assert any(item.kind == "package-manager-mismatch" for item in findings)


def test_missing_package_script_is_reported(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Validate with §npm run lint§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert any(item.kind == "missing-package-script" for item in findings)
    assert finding_summary(findings)["invalid_commands"] == 1


def test_cross_agent_validation_drift_is_reported(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest", "test:unit": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("Run §npm test§.\n".replace("§", "`"), encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("Run §npm run test:unit§.\n".replace("§", "`"), encoding="utf-8")

    findings = lint_instructions(tmp_path)

    assert any(item.kind == "validation-command-drift" for item in findings)


def test_shared_validation_command_avoids_false_positive_drift(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest", "test:e2e": "playwright test"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run §npm test§ and §npm run test:e2e§.\n".replace("§", "`"),
        encoding="utf-8",
    )
    (tmp_path / "CLAUDE.md").write_text("Run §npm test§.\n".replace("§", "`"), encoding="utf-8")

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "validation-command-drift" for item in findings)


def test_fix_plan_is_previewable_and_non_destructive(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    plan = build_fix_plan(tmp_path)

    assert any(item.kind == "create-agents" and item.apply_supported for item in plan)
    assert not (tmp_path / "AGENTS.md").exists()


def test_apply_fix_plan_only_creates_missing_agents(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    plan = build_fix_plan(tmp_path)

    applied = apply_fix_plan(tmp_path, plan)

    assert applied
    assert (tmp_path / "AGENTS.md").exists()


def test_fix_plan_never_auto_rewrites_conflicting_instructions(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@9.0.0",
                "scripts": {"test": "vitest"},
            }
        ),
        encoding="utf-8",
    )
    original = "Run §npm test§.\n".replace("§", "`")
    (tmp_path / "AGENTS.md").write_text(original, encoding="utf-8")

    plan = build_fix_plan(tmp_path)
    apply_fix_plan(tmp_path, plan)

    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == original
    assert any(not item.apply_supported for item in plan)


def test_detect_instruction_signals_deduplicates_clinerules_file(tmp_path: Path) -> None:
    (tmp_path / ".clinerules").write_text("rules\n", encoding="utf-8")

    signals = detect_instruction_signals(tmp_path)

    assert [(item.tool, item.path) for item in signals].count(("Cline", ".clinerules")) == 1


def test_nested_agents_scope_and_override_precedence(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("root\n", encoding="utf-8")
    nested = tmp_path / "services" / "payments"
    nested.mkdir(parents=True)
    (nested / "AGENTS.md").write_text("nested\n", encoding="utf-8")
    (nested / "AGENTS.override.md").write_text("override\n", encoding="utf-8")

    signals = detect_instruction_signals(tmp_path)
    pairs = {(item.path, item.scope, item.kind) for item in signals}

    assert ("AGENTS.md", ".", "repository") in pairs
    assert ("services/payments/AGENTS.override.md", "services/payments", "override") in pairs
    assert not any(item.path == "services/payments/AGENTS.md" for item in signals)


def test_path_specific_frontmatter_sets_scope(tmp_path: Path) -> None:
    instructions = tmp_path / ".github" / "instructions"
    instructions.mkdir(parents=True)
    (instructions / "python.instructions.md").write_text(
        "---\napplyTo: \"services/api/**/*.py\"\n---\nRun §python -m pytest§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    signals = detect_instruction_signals(tmp_path)
    signal = next(item for item in signals if item.path.endswith("python.instructions.md"))

    assert signal.scope == "services/api"
    assert signal.kind == "path-specific"


def test_continue_globs_sets_scope(tmp_path: Path) -> None:
    rules = tmp_path / ".continue" / "rules"
    rules.mkdir(parents=True)
    (rules / "intellij.md").write_text(
        "---\nglobs: extensions/intellij/**/*Test.kt\nalwaysApply: false\n---\n"
        "Run §./gradlew test§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    signal = next(
        item
        for item in detect_instruction_signals(tmp_path)
        if item.path.endswith("intellij.md")
    )

    assert signal.scope == "extensions/intellij"


def test_different_scopes_do_not_create_validation_drift(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest", "test:unit": "vitest run"}}),
        encoding="utf-8",
    )
    root = "Run §npm test§.\n".replace("§", "`")
    (tmp_path / "AGENTS.md").write_text(root, encoding="utf-8")

    instructions = tmp_path / ".github" / "instructions"
    instructions.mkdir(parents=True)
    (instructions / "api.instructions.md").write_text(
        "---\napplyTo: \"services/api/**\"\n---\nRun §npm run test:unit§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "validation-command-drift" for item in findings)


def test_nested_scope_uses_nearest_package_manager_evidence(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "npm@11", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    app = tmp_path / "apps" / "web"
    app.mkdir(parents=True)
    (app / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (app / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (app / "AGENTS.md").write_text("Run §pnpm test§.\n".replace("§", "`"), encoding="utf-8")

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "package-manager-mismatch" for item in findings)


def test_broader_validation_commands_are_recognized() -> None:
    text = """
§§§bash
uv run pytest -q
just test
./gradlew test
./mvnw test
dotnet test
§§§
""".replace("§", "`")

    commands = extract_commands(text)

    assert "uv run pytest -q" in commands
    assert "just test" in commands
    assert "./gradlew test" in commands
    assert "./mvnw test" in commands
    assert "dotnet test" in commands


def test_copilot_instruction_directory_ignores_unrelated_files(tmp_path: Path) -> None:
    directory = tmp_path / ".github" / "instructions"
    directory.mkdir(parents=True)
    (directory / "README.md").write_text("not an instruction\n", encoding="utf-8")
    (directory / "python.instructions.md").write_text(
        "---\napplyTo: \"**/*.py\"\n---\nRun §python -m pytest§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    paths = {item.path for item in detect_instruction_signals(tmp_path)}

    assert ".github/instructions/python.instructions.md" in paths
    assert ".github/instructions/README.md" not in paths


def test_missing_copilot_applyto_is_reported(tmp_path: Path) -> None:
    directory = tmp_path / ".github" / "instructions"
    directory.mkdir(parents=True)
    (directory / "python.instructions.md").write_text(
        "Run §python -m pytest§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert any(item.kind == "missing-scope-metadata" for item in findings)
    assert finding_summary(findings)["metadata"] == 1
    assert finding_summary(findings)["invalid_commands"] == 0


def test_conflicting_package_manager_evidence_is_reported_once_per_scope(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10",
                "scripts": {"test": "vitest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Run §pnpm test§.\n".replace("§", "`"), encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("Run §pnpm test§.\n".replace("§", "`"), encoding="utf-8")

    findings = lint_instructions(tmp_path)
    conflicts = [item for item in findings if item.kind == "package-manager-evidence-conflict"]

    assert len(conflicts) == 1
    assert set(conflicts[0].evidence) == {"npm", "pnpm"}


def test_fix_plan_does_not_add_agents_when_repo_wide_baseline_exists(tmp_path: Path) -> None:
    github = tmp_path / ".github"
    github.mkdir()
    (github / "copilot-instructions.md").write_text("Use existing repository rules.\n", encoding="utf-8")

    plan = build_fix_plan(tmp_path)

    assert not any(item.kind == "create-agents" for item in plan)


def test_path_specific_rules_with_same_static_prefix_are_not_cross_compared(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "test": "vitest",
                    "test:unit": "vitest run",
                }
            }
        ),
        encoding="utf-8",
    )
    directory = tmp_path / ".github" / "instructions"
    directory.mkdir(parents=True)
    (directory / "python.instructions.md").write_text(
        "---\napplyTo: \"**/*.py\"\n---\nRun §npm test§.\n".replace("§", "`"),
        encoding="utf-8",
    )
    (directory / "typescript.instructions.md").write_text(
        "---\napplyTo: \"**/*.ts\"\n---\nRun §npm run test:unit§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "validation-command-drift" for item in findings)


def test_nested_cursor_rules_preserve_directory_scope(tmp_path: Path) -> None:
    rules = tmp_path / "backend" / "server" / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "always.mdc").write_text(
        "---\nalwaysApply: true\nglobs:\n---\nUse §just test§.\n".replace("§", "`"),
        encoding="utf-8",
    )
    (rules / "python.mdc").write_text(
        "---\nalwaysApply: false\nglobs: **/*.py\n---\nUse §python -m pytest§.\n".replace("§", "`"),
        encoding="utf-8",
    )
    (rules / "manual.mdc").write_text(
        "---\nalwaysApply: false\nglobs:\ndescription: Manual helper\n---\nUse §just lint§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    signals = detect_instruction_signals(tmp_path)
    by_name = {Path(item.path).name: item for item in signals if item.tool == "Cursor"}

    assert by_name["always.mdc"].scope == "backend/server"
    assert by_name["always.mdc"].kind == "repository"
    assert by_name["python.mdc"].scope == "backend/server"
    assert by_name["python.mdc"].kind == "path-specific"
    assert by_name["manual.mdc"].scope == "backend/server"
    assert by_name["manual.mdc"].kind == "conditional"


def test_cursor_rules_ignore_non_mdc_files(tmp_path: Path) -> None:
    rules = tmp_path / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "README.md").write_text("documentation only\n", encoding="utf-8")
    (rules / "rule.mdc").write_text(
        "---\nalwaysApply: true\n---\nUse repository rules.\n",
        encoding="utf-8",
    )

    paths = {item.path for item in detect_instruction_signals(tmp_path)}

    assert ".cursor/rules/rule.mdc" in paths
    assert ".cursor/rules/README.md" not in paths


def test_cursor_multiline_globs_set_common_scope(tmp_path: Path) -> None:
    rules = tmp_path / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "typescript.mdc").write_text(
        "---\n"
        "globs:\n"
        "  - \"apps/web/src/**/*.ts\"\n"
        "  - \"apps/web/tests/**/*.ts\"\n"
        "alwaysApply: false\n"
        "---\n"
        "Run §pnpm test§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    signal = next(
        item
        for item in detect_instruction_signals(tmp_path)
        if item.path.endswith("typescript.mdc")
    )

    assert signal.scope == "apps/web"
    assert signal.kind == "path-specific"


def test_multiline_globs_stop_at_next_frontmatter_key(tmp_path: Path) -> None:
    rules = tmp_path / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "python.mdc").write_text(
        "---\n"
        "globs:\n"
        "  - \"services/api/**/*.py\"\n"
        "description: API Python rules\n"
        "alwaysApply: false\n"
        "---\n"
        "Run §python -m pytest§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    signal = next(
        item
        for item in detect_instruction_signals(tmp_path)
        if item.path.endswith("python.mdc")
    )

    assert signal.scope == "services/api"
    assert signal.kind == "path-specific"


def test_instruction_discovery_prunes_large_generated_directories(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("root\n", encoding="utf-8")

    ignored_agents = tmp_path / "node_modules" / "pkg"
    ignored_agents.mkdir(parents=True)
    (ignored_agents / "AGENTS.md").write_text("ignore me\n", encoding="utf-8")

    ignored_cursor = tmp_path / ".venv" / "nested" / ".cursor" / "rules"
    ignored_cursor.mkdir(parents=True)
    (ignored_cursor / "rule.mdc").write_text(
        "---\nalwaysApply: true\n---\nignore me\n",
        encoding="utf-8",
    )

    valid_cursor = tmp_path / ".cursor" / "rules"
    valid_cursor.mkdir(parents=True)
    (valid_cursor / "rule.mdc").write_text(
        "---\nalwaysApply: true\n---\nUse repository rules.\n",
        encoding="utf-8",
    )

    paths = {item.path for item in detect_instruction_signals(tmp_path)}

    assert "AGENTS.md" in paths
    assert ".cursor/rules/rule.mdc" in paths
    assert "node_modules/pkg/AGENTS.md" not in paths
    assert ".venv/nested/.cursor/rules/rule.mdc" not in paths


def test_package_manager_flags_do_not_become_fake_scripts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10",
                "scripts": {"test": "vitest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Run §pnpm --filter web test§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)
    assert not any(item.kind == "package-manager-mismatch" for item in findings)


def test_npm_workspace_flag_is_not_treated_as_script(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "npm@11",
                "scripts": {"test": "vitest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Run §npm --workspace app run test§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_nested_claude_md_uses_directory_scope(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("root rules\n", encoding="utf-8")
    nested = tmp_path / "services" / "api"
    nested.mkdir(parents=True)
    (nested / "CLAUDE.md").write_text("Run §python -m pytest§.\n".replace("§", "`"), encoding="utf-8")

    signals = detect_instruction_signals(tmp_path)
    by_path = {item.path: item for item in signals if item.tool == "Claude Code"}

    assert by_path["CLAUDE.md"].scope == "."
    assert by_path["services/api/CLAUDE.md"].scope == "services/api"


def test_nested_claude_md_uses_nearest_package_manager_evidence(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "npm@11", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    app = tmp_path / "apps" / "web"
    app.mkdir(parents=True)
    (app / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (app / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (app / "CLAUDE.md").write_text(
        "Run §pnpm test§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "package-manager-mismatch" for item in findings)


def test_nested_gemini_md_uses_directory_scope(tmp_path: Path) -> None:
    (tmp_path / "GEMINI.md").write_text("root rules\n", encoding="utf-8")
    nested = tmp_path / "packages" / "worker"
    nested.mkdir(parents=True)
    (nested / "GEMINI.md").write_text(
        "Run §pnpm test§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    signals = detect_instruction_signals(tmp_path)
    by_path = {item.path: item for item in signals if item.tool == "Gemini CLI"}

    assert by_path["GEMINI.md"].scope == "."
    assert by_path["packages/worker/GEMINI.md"].scope == "packages/worker"


def test_nested_gemini_md_uses_nearest_package_manager_evidence(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "npm@11", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    app = tmp_path / "packages" / "worker"
    app.mkdir(parents=True)
    (app / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (app / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (app / "GEMINI.md").write_text(
        "Run §pnpm test§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "package-manager-mismatch" for item in findings)


def test_gemini_project_setting_customizes_context_filename(tmp_path: Path) -> None:
    settings = tmp_path / ".gemini"
    settings.mkdir()
    (settings / "settings.json").write_text(
        json.dumps({"context": {"fileName": "CONTEXT.md"}}),
        encoding="utf-8",
    )
    (tmp_path / "GEMINI.md").write_text("default should be ignored\n", encoding="utf-8")
    (tmp_path / "CONTEXT.md").write_text("custom root\n", encoding="utf-8")
    nested = tmp_path / "services" / "api"
    nested.mkdir(parents=True)
    (nested / "CONTEXT.md").write_text("custom nested\n", encoding="utf-8")

    signals = [item for item in detect_instruction_signals(tmp_path) if item.tool == "Gemini CLI"]
    by_path = {item.path: item for item in signals}

    assert "GEMINI.md" not in by_path
    assert by_path["CONTEXT.md"].scope == "."
    assert by_path["services/api/CONTEXT.md"].scope == "services/api"


def test_gemini_project_setting_accepts_context_filename_list(tmp_path: Path) -> None:
    settings = tmp_path / ".gemini"
    settings.mkdir()
    (settings / "settings.json").write_text(
        json.dumps({"context": {"fileName": ["AGENTS.md", "GEMINI.md", "AGENTS.md"]}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("shared instructions\n", encoding="utf-8")
    (tmp_path / "GEMINI.md").write_text("gemini instructions\n", encoding="utf-8")

    signals = detect_instruction_signals(tmp_path)
    gemini_paths = [item.path for item in signals if item.tool == "Gemini CLI"]

    assert gemini_paths.count("AGENTS.md") == 1
    assert gemini_paths.count("GEMINI.md") == 1


def test_invalid_gemini_settings_fall_back_to_default_context_filename(tmp_path: Path) -> None:
    settings = tmp_path / ".gemini"
    settings.mkdir()
    (settings / "settings.json").write_text("{not-json", encoding="utf-8")
    (tmp_path / "GEMINI.md").write_text("default context\n", encoding="utf-8")

    signals = detect_instruction_signals(tmp_path)

    assert any(item.tool == "Gemini CLI" and item.path == "GEMINI.md" for item in signals)


def test_chained_package_commands_are_extracted_individually() -> None:
    commands = extract_commands("Run §npm test && npm run lint§ before committing.\n".replace("§", "`"))

    assert "npm test" in commands
    assert "npm run lint" in commands


def test_chained_commands_enable_missing_script_detection(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run §npm test && npm run lint§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    missing = [item for item in findings if item.kind == "missing-package-script"]
    assert len(missing) == 1
    assert any("lint" in item.message for item in missing)


def test_shell_chain_splitter_does_not_split_quoted_separators() -> None:
    commands = extract_commands(
        "Run §npm run test -- --grep 'a && b' && npm run lint§.\n".replace("§", "`")
    )

    assert any(command.startswith("npm run test") for command in commands)
    assert "npm run lint" in commands


def test_instruction_discovery_ignores_symlinked_instruction_files(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("Run §npm test§.\n".replace("§", "`"), encoding="utf-8")

    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        if path == target:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    signals = detect_instruction_signals(tmp_path)

    assert not any(item.path == "AGENTS.md" for item in signals)


def test_package_manager_evidence_ignores_symlinked_package_json(tmp_path: Path, monkeypatch) -> None:
    package = tmp_path / "package.json"
    package.write_text(
        json.dumps({"packageManager": "npm@11", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Run §pnpm test§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        if path == package:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "package-manager-evidence-conflict" for item in findings)
    assert not any(item.kind == "package-manager-mismatch" for item in findings)


def test_apply_fix_plan_does_not_write_through_symlink_target(tmp_path: Path, monkeypatch) -> None:
    plan = build_fix_plan(tmp_path)
    target = tmp_path / "AGENTS.md"

    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        if path == target:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    applied = apply_fix_plan(tmp_path, plan)

    assert applied == []
    assert not target.exists()


def test_pnpm_filter_command_validates_real_script_name(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10",
                "scripts": {"test": "vitest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    web = tmp_path / "packages" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text(
        json.dumps({"name": "web", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run §pnpm --filter web run lint§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    missing = [item for item in findings if item.kind == "missing-package-script"]
    assert len(missing) == 1
    assert "lint" in missing[0].message


def test_pnpm_directory_flag_validates_real_script_name(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10",
                "scripts": {"test": "vitest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Run §pnpm -C apps/web test§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_npm_workspace_flag_validates_real_script_name(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "npm@11",
                "scripts": {"test": "vitest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    app = tmp_path / "packages" / "app"
    app.mkdir(parents=True)
    (app / "package.json").write_text(
        json.dumps({"name": "app", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run §npm --workspace app run lint§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    missing = [item for item in findings if item.kind == "missing-package-script"]
    assert len(missing) == 1
    assert "lint" in missing[0].message


def test_yarn_workspace_command_validates_real_script_name(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "yarn@4",
                "scripts": {"test": "vitest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "yarn.lock").write_text("", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Run §yarn workspace web test§.\n".replace("§", "`"),
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)
    assert not any(item.kind == "package-manager-mismatch" for item in findings)


def test_embedded_brace_glob_keeps_parent_static_scope(tmp_path: Path) -> None:
    directory = tmp_path / ".github" / "instructions"
    directory.mkdir(parents=True)
    (directory / "web.instructions.md").write_text(
        "---\n"
        'applyTo: "apps/web/{src,tests}/**/*.ts"\n'
        "---\n"
        "Use web validation.\n",
        encoding="utf-8",
    )

    signals = detect_instruction_signals(tmp_path)
    signal = next(
        item
        for item in signals
        if item.path == ".github/instructions/web.instructions.md"
    )

    assert signal.kind == "path-specific"
    assert signal.scope == "apps/web"


def test_pnpm_filter_validates_target_workspace_script(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@11", "scripts": {"test": "turbo test"}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    package = tmp_path / "packages" / "core"
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps({"name": "@demo/core", "scripts": {"dev": "vite"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `pnpm --filter @demo/core run dev`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_pnpm_filter_reports_script_missing_from_target_workspace(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@11", "scripts": {"dev": "vite"}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    package = tmp_path / "packages" / "core"
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps({"name": "@demo/core", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `pnpm --filter @demo/core run dev`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    missing = [item for item in findings if item.kind == "missing-package-script"]
    assert len(missing) == 1
    assert "dev" in missing[0].message


def test_npm_workspace_validates_target_workspace_script(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "npm@11", "scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")
    package = tmp_path / "packages" / "web"
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps({"name": "@demo/web", "scripts": {"lint": "eslint ."}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `npm --workspace @demo/web run lint`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_yarn_workspace_validates_target_workspace_script(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "yarn@4", "scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "yarn.lock").write_text("", encoding="utf-8")
    package = tmp_path / "packages" / "web"
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps({"name": "@demo/web", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `yarn workspace @demo/web test`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_unresolved_workspace_selector_does_not_fall_back_to_root_scripts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@11", "scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Run `pnpm --filter './packages/**' run test`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_pnpm_directory_target_uses_target_package_scripts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps({"scripts": {"test": "jest"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `pnpm -C frontend test`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_pnpm_directory_target_reports_missing_script_in_target(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {"lint": "eslint ."}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps({"scripts": {"test": "jest"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `pnpm --dir=frontend run lint`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    missing = [item for item in findings if item.kind == "missing-package-script"]
    assert len(missing) == 1
    assert "lint" in missing[0].message


def test_directory_target_path_traversal_does_not_read_outside_repo(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Run `pnpm -C ../outside run test`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_extract_commands_keeps_yarn_inline_cwd_value() -> None:
    commands = extract_commands(
        "Preview with `yarn --cwd=website start` and validate with "
        "`yarn --cwd=website build`."
    )

    assert "yarn --cwd=website start" in commands
    assert "yarn --cwd=website build" in commands


def test_yarn_inline_cwd_uses_target_package_scripts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "yarn@4", "scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "yarn.lock").write_text("", encoding="utf-8")
    website = tmp_path / "website"
    website.mkdir()
    (website / "package.json").write_text(
        json.dumps({"scripts": {"start": "docusaurus start"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `yarn --cwd=website start`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_yarn_inline_cwd_reports_missing_script_in_target(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "yarn@4", "scripts": {"build": "echo root"}}),
        encoding="utf-8",
    )
    (tmp_path / "yarn.lock").write_text("", encoding="utf-8")
    website = tmp_path / "website"
    website.mkdir()
    (website / "package.json").write_text(
        json.dumps({"scripts": {"start": "docusaurus start"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `yarn --cwd=website run build`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    missing = [item for item in findings if item.kind == "missing-package-script"]
    assert len(missing) == 1
    assert "build" in missing[0].message


def test_npm_post_script_workspace_flags_use_target_package_scripts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "npm@11", "scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")
    web = tmp_path / "packages" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text(
        json.dumps({"name": "@demo/web", "scripts": {"lint": "eslint ."}}),
        encoding="utf-8",
    )

    commands = (
        "npm run lint --workspace=@demo/web",
        "npm run lint --workspace @demo/web",
        "npm run lint -w @demo/web",
        "npm run lint -w=@demo/web",
    )
    for command in commands:
        (tmp_path / "AGENTS.md").write_text(
            f"Run `{command}`.\n",
            encoding="utf-8",
        )
        findings = lint_instructions(tmp_path)
        assert not any(
            item.kind == "missing-package-script"
            for item in findings
        ), command


def test_npm_post_script_workspace_reports_missing_script_in_target(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "npm@11", "scripts": {"lint": "eslint root"}}),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")
    web = tmp_path / "packages" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text(
        json.dumps({"name": "@demo/web", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `npm run lint --workspace=@demo/web`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    missing = [item for item in findings if item.kind == "missing-package-script"]
    assert len(missing) == 1
    assert "lint" in missing[0].message


def test_npm_script_argument_separator_stops_workspace_resolution(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "npm@11", "scripts": {"test": "vitest root"}}),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")
    web = tmp_path / "packages" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text(
        json.dumps({"name": "@demo/web", "scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `npm run test -- --workspace=@demo/web`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_safe_claude_agents_alias_is_detected_without_following_link(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "Run `npm run lint`.\n",
        encoding="utf-8",
    )
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("AGENTS.md", encoding="utf-8")

    original_is_symlink = Path.is_symlink
    original_readlink = Path.readlink

    def fake_is_symlink(path: Path) -> bool:
        if path == claude:
            return True
        return original_is_symlink(path)

    def fake_readlink(path: Path) -> Path:
        if path == claude:
            return Path("AGENTS.md")
        return original_readlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "readlink", fake_readlink)

    signals = detect_instruction_signals(tmp_path)
    alias = next(
        item
        for item in signals
        if item.tool == "Claude Code" and item.path == "CLAUDE.md"
    )

    assert alias.kind == "alias"
    findings = lint_instructions(tmp_path, [alias])
    assert any(item.kind == "missing-package-script" for item in findings)


def test_claude_alias_rejects_parent_traversal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "AGENTS.md").write_text("root\n", encoding="utf-8")
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("../AGENTS.md", encoding="utf-8")

    original_is_symlink = Path.is_symlink
    original_readlink = Path.readlink

    def fake_is_symlink(path: Path) -> bool:
        if path == claude:
            return True
        return original_is_symlink(path)

    def fake_readlink(path: Path) -> Path:
        if path == claude:
            return Path("../AGENTS.md")
        return original_readlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "readlink", fake_readlink)

    signals = detect_instruction_signals(tmp_path)

    assert not any(
        item.tool == "Claude Code" and item.path == "CLAUDE.md"
        for item in signals
    )


def test_claude_alias_rejects_symlinked_agents_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("root\n", encoding="utf-8")
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("AGENTS.md", encoding="utf-8")

    original_is_symlink = Path.is_symlink
    original_readlink = Path.readlink

    def fake_is_symlink(path: Path) -> bool:
        if path in {claude, agents}:
            return True
        return original_is_symlink(path)

    def fake_readlink(path: Path) -> Path:
        if path == claude:
            return Path("AGENTS.md")
        return original_readlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "readlink", fake_readlink)

    signals = detect_instruction_signals(tmp_path)

    assert not any(
        item.tool == "Claude Code" and item.path == "CLAUDE.md"
        for item in signals
    )


def test_safe_gemini_agents_alias_is_detected_and_linted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "Run `npm run lint`.\n",
        encoding="utf-8",
    )
    gemini = tmp_path / "GEMINI.md"
    gemini.write_text("AGENTS.md", encoding="utf-8")

    original_is_symlink = Path.is_symlink
    original_readlink = Path.readlink

    def fake_is_symlink(path: Path) -> bool:
        if path == gemini:
            return True
        return original_is_symlink(path)

    def fake_readlink(path: Path) -> Path:
        if path == gemini:
            return Path("AGENTS.md")
        return original_readlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "readlink", fake_readlink)

    signals = detect_instruction_signals(tmp_path)
    alias = next(
        item
        for item in signals
        if item.tool == "Gemini CLI" and item.path == "GEMINI.md"
    )

    assert alias.kind == "alias"
    findings = lint_instructions(tmp_path, [alias])
    assert any(item.kind == "missing-package-script" for item in findings)


def test_gemini_alias_is_not_used_when_context_filename_excludes_gemini(
    tmp_path: Path,
    monkeypatch,
) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("Use shared instructions.\n", encoding="utf-8")
    gemini = tmp_path / "GEMINI.md"
    gemini.write_text("AGENTS.md", encoding="utf-8")
    settings = tmp_path / ".gemini"
    settings.mkdir()
    (settings / "settings.json").write_text(
        json.dumps({"context": {"fileName": ["AGENTS.md"]}}),
        encoding="utf-8",
    )

    original_is_symlink = Path.is_symlink
    original_readlink = Path.readlink

    def fake_is_symlink(path: Path) -> bool:
        if path == gemini:
            return True
        return original_is_symlink(path)

    def fake_readlink(path: Path) -> Path:
        if path == gemini:
            return Path("AGENTS.md")
        return original_readlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "readlink", fake_readlink)

    signals = detect_instruction_signals(tmp_path)

    assert any(
        item.tool == "Gemini CLI" and item.path == "AGENTS.md"
        for item in signals
    )
    assert not any(
        item.tool == "Gemini CLI" and item.path == "GEMINI.md"
        for item in signals
    )


def test_pnpm_exact_path_filter_uses_target_package_scripts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    api = tmp_path / "api"
    api.mkdir()
    (api / "package.json").write_text(
        json.dumps({"name": "@demo/api", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `pnpm --filter ./api test`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_pnpm_exact_path_filter_reports_missing_script_in_target(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {"lint": "eslint root"}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    api = tmp_path / "api"
    api.mkdir()
    (api / "package.json").write_text(
        json.dumps({"name": "@demo/api", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `pnpm --filter ./api run lint`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    missing = [item for item in findings if item.kind == "missing-package-script"]
    assert len(missing) == 1
    assert "lint" in missing[0].message


def test_pnpm_complex_path_filter_stays_unresolved(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    api = tmp_path / "api"
    api.mkdir()
    (api / "package.json").write_text(
        json.dumps({"name": "@demo/api", "scripts": {}}),
        encoding="utf-8",
    )

    for selector in ("./api...", "./packages/**", "./../outside"):
        (tmp_path / "AGENTS.md").write_text(
            f"Run `pnpm --filter '{selector}' run lint`.\n",
            encoding="utf-8",
        )
        findings = lint_instructions(tmp_path)
        assert not any(item.kind == "missing-package-script" for item in findings), selector


def test_extract_commands_stays_stable_for_cd_package_chain() -> None:
    commands = extract_commands("Run `cd frontend && pnpm test`.")

    assert commands == ["pnpm test"]


def test_cd_context_uses_target_package_scripts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {"lint": "eslint ."}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `cd frontend && pnpm test`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_cd_context_reports_missing_script_in_target(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {"test": "vitest root"}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {"lint": "eslint ."}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `cd frontend && pnpm test`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    missing = [item for item in findings if item.kind == "missing-package-script"]
    assert len(missing) == 1
    assert "after cd 'frontend'" in missing[0].message


def test_quoted_cd_context_uses_target_package_scripts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "npm@11", "scripts": {}}),
        encoding="utf-8",
    )
    frontend = tmp_path / "frontend app"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        'Run `cd "frontend app" && npm test`.\n',
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_unsafe_cd_context_does_not_fall_back_to_root_scripts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Run `cd ../outside && pnpm test`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_cd_context_with_nested_package_routing_stays_unresolved(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10", "scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps({"scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `cd frontend && pnpm --filter ./app run test`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)

