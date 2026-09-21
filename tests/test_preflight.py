from pathlib import Path
import shutil
import subprocess

import pytest

from codex_workspace_bootstrap.audit import Check
from codex_workspace_bootstrap.preflight import (
    build_preflight,
    detect_instruction_signals,
    readiness_state,
    render_markdown,
)


def test_detect_instruction_signals_across_agents(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# claude\n", encoding="utf-8")
    (tmp_path / ".github" / "instructions").mkdir(parents=True)
    (tmp_path / ".github" / "instructions" / "python.instructions.md").write_text(
        "# copilot\n",
        encoding="utf-8",
    )
    (tmp_path / ".cursor" / "rules").mkdir(parents=True)
    (tmp_path / ".cursor" / "rules" / "repo.mdc").write_text("# cursor\n", encoding="utf-8")
    (tmp_path / ".clinerules").mkdir()
    (tmp_path / ".clinerules" / "coding.md").write_text("# cline\n", encoding="utf-8")

    signals = detect_instruction_signals(tmp_path)
    pairs = {(item.tool, item.path) for item in signals}

    assert ("Codex / OpenAI agents", "AGENTS.md") in pairs
    assert ("Claude Code", "CLAUDE.md") in pairs
    assert ("GitHub Copilot", ".github/instructions/python.instructions.md") in pairs
    assert ("Cursor", ".cursor/rules/repo.mdc") in pairs
    assert ("Cline", ".clinerules/coding.md") in pairs


def test_readiness_is_blocked_when_a_blocking_check_exists() -> None:
    checks = [Check("secret-risk-files", "warn", "tracked risky file", blocking=True)]

    assert readiness_state(checks, []) == "BLOCKED"


def test_readiness_needs_attention_without_ai_instructions() -> None:
    checks = [
        Check("git-repository", "pass", "ok"),
        Check("readme", "pass", "ok"),
        Check("gitignore", "pass", "ok"),
        Check("project-manifest", "pass", "ok"),
    ]

    assert readiness_state(checks, []) == "NEEDS ATTENTION"


def test_readiness_is_ready_with_essentials_and_instruction_signal() -> None:
    from codex_workspace_bootstrap.preflight import InstructionSignal

    checks = [
        Check("git-repository", "pass", "ok"),
        Check("readme", "pass", "ok"),
        Check("gitignore", "pass", "ok"),
        Check("project-manifest", "pass", "ok"),
    ]

    assert readiness_state(checks, [InstructionSignal("Codex / OpenAI agents", "AGENTS.md")]) == "READY"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_build_preflight_prioritizes_missing_instructions(tmp_path: Path) -> None:
    subprocess.run(("git", "-C", str(tmp_path), "init"), check=True, capture_output=True, text=True)
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    report = build_preflight(tmp_path)

    assert report["state"] == "NEEDS ATTENTION"
    actions = report["next_actions"]
    assert any(item["command"] == "cwb init-agents ." for item in actions)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_markdown_report_is_human_readable(tmp_path: Path) -> None:
    subprocess.run(("git", "-C", str(tmp_path), "init"), check=True, capture_output=True, text=True)
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# agents\n", encoding="utf-8")

    markdown = render_markdown(build_preflight(tmp_path))

    assert "# AI Repository Preflight" in markdown
    assert "**State:** READY" in markdown
    assert "Codex / OpenAI agents" in markdown


def test_readiness_needs_attention_with_only_scoped_instruction() -> None:
    from codex_workspace_bootstrap.preflight import InstructionSignal

    checks = [
        Check("git-repository", "pass", "ok"),
        Check("readme", "pass", "ok"),
        Check("gitignore", "pass", "ok"),
        Check("project-manifest", "pass", "ok"),
    ]

    scoped = InstructionSignal(
        "GitHub Copilot",
        ".github/instructions/python.instructions.md",
        "services/api",
        "path-specific",
    )

    assert readiness_state(checks, [scoped]) == "NEEDS ATTENTION"


def test_root_prefix_path_specific_rule_is_not_repository_wide() -> None:
    from codex_workspace_bootstrap.preflight import InstructionSignal

    checks = [
        Check("git-repository", "pass", "ok"),
        Check("readme", "pass", "ok"),
        Check("gitignore", "pass", "ok"),
        Check("project-manifest", "pass", "ok"),
    ]

    path_rule = InstructionSignal(
        "GitHub Copilot",
        ".github/instructions/python.instructions.md",
        ".",
        "path-specific",
    )

    assert readiness_state(checks, [path_rule]) == "NEEDS ATTENTION"
