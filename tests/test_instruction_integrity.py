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
