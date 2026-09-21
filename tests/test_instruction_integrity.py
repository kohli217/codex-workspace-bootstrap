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
        json.dumps({"scripts": {"test": "vitest", "lint": "eslint ."}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("Run §npm test§.\n".replace("§", "`"), encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("Run §npm run lint§.\n".replace("§", "`"), encoding="utf-8")

    findings = lint_instructions(tmp_path)

    assert any(item.kind == "validation-command-drift" for item in findings)


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
