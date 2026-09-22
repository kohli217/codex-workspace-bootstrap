from pathlib import Path
import shutil
import subprocess

import pytest

from codex_workspace_bootstrap.audit import Check
from codex_workspace_bootstrap.preflight import (
    PREFLIGHT_REPORT_SCHEMA_VERSION,
    build_preflight,
    detect_instruction_signals,
    evaluate_preflight_policy,
    readiness_state,
    next_actions,
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


def test_conditional_cursor_rule_is_not_repository_wide_baseline() -> None:
    from codex_workspace_bootstrap.preflight import InstructionSignal

    checks = [
        Check("git-repository", "pass", "ok"),
        Check("readme", "pass", "ok"),
        Check("gitignore", "pass", "ok"),
        Check("project-manifest", "pass", "ok"),
    ]

    conditional = InstructionSignal(
        "Cursor",
        ".cursor/rules/manual.mdc",
        ".",
        "conditional",
    )

    assert readiness_state(checks, [conditional]) == "NEEDS ATTENTION"


def test_next_actions_recommends_detected_pnpm_toolchain() -> None:
    checks = [
        Check("pnpm", "warn", "pnpm command not found"),
    ]

    actions = next_actions(
        checks,
        [],
        ["Node.js"],
    )

    assert any(
        item.command == "pnpm --version"
        and "Node.js/pnpm" in item.title
        for item in actions
    )
    assert not any(item.command == "npm --version" for item in actions)


def test_next_actions_asks_to_confirm_package_manager_when_unproven() -> None:
    checks = [
        Check(
            "package-manager-evidence",
            "warn",
            "Node.js project detected, but package manager evidence is missing",
        ),
    ]

    actions = next_actions(
        checks,
        [],
        ["Node.js"],
    )

    assert any(item.title == "Confirm the repository package manager" for item in actions)
    assert not any(item.command and item.command.endswith("--version") for item in actions)


def test_next_actions_prioritizes_conflicting_package_manager_evidence() -> None:
    checks = [
        Check(
            "package-manager-evidence",
            "warn",
            "Conflicting Node.js package-manager evidence detected: npm, pnpm",
        ),
        Check("npm", "pass", "available"),
        Check("pnpm", "pass", "available"),
    ]

    actions = next_actions(
        checks,
        [],
        ["Node.js"],
    )

    assert any(
        item.priority == "P1"
        and item.title == "Resolve conflicting repository package-manager evidence"
        for item in actions
    )


def test_build_preflight_deduplicates_root_package_manager_conflict(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "package.json").write_text(
        '{"packageManager":"pnpm@10","scripts":{"test":"vitest"}}',
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Run §pnpm test§.\n".replace("§", "`"), encoding="utf-8")

    def fake_tool_check(label: str, command: tuple[str, ...]):
        return Check(label, "pass", "available")

    monkeypatch.setattr("codex_workspace_bootstrap.audit._tool_check", fake_tool_check)

    report = build_preflight(tmp_path)

    audit_conflicts = [
        item
        for item in report["checks"]
        if item["name"] == "package-manager-evidence"
        and item["message"].startswith("Conflicting Node.js package-manager evidence")
    ]
    instruction_conflicts = [
        item
        for item in report["instruction_findings"]
        if item["kind"] == "package-manager-evidence-conflict"
        and item["scope"] == "."
    ]
    conflict_actions = [
        item
        for item in report["next_actions"]
        if "package-manager" in item["title"].lower()
        and "conflict" in item["title"].lower()
    ]

    assert len(audit_conflicts) == 1
    assert instruction_conflicts == []
    assert len(conflict_actions) == 1


def test_build_preflight_keeps_nested_package_manager_conflict(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "package.json").write_text(
        '{"packageManager":"npm@11","scripts":{"test":"vitest"}}',
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Run §npm test§.\n".replace("§", "`"), encoding="utf-8")

    nested = tmp_path / "apps" / "web"
    nested.mkdir(parents=True)
    (nested / "package.json").write_text(
        '{"packageManager":"pnpm@10","scripts":{"test":"vitest"}}',
        encoding="utf-8",
    )
    (nested / "package-lock.json").write_text("{}", encoding="utf-8")
    (nested / "AGENTS.md").write_text("Run §pnpm test§.\n".replace("§", "`"), encoding="utf-8")

    def fake_tool_check(label: str, command: tuple[str, ...]):
        return Check(label, "pass", "available")

    monkeypatch.setattr("codex_workspace_bootstrap.audit._tool_check", fake_tool_check)

    report = build_preflight(tmp_path)

    nested_conflicts = [
        item
        for item in report["instruction_findings"]
        if item["kind"] == "package-manager-evidence-conflict"
        and item["scope"] == "apps/web"
    ]

    assert len(nested_conflicts) == 1


def test_preflight_report_declares_schema_version(tmp_path: Path) -> None:
    report = build_preflight(tmp_path)

    assert report["schema_version"] == PREFLIGHT_REPORT_SCHEMA_VERSION
    assert PREFLIGHT_REPORT_SCHEMA_VERSION == 1


@pytest.mark.parametrize(
    ("report", "options", "expected_passed", "expected_failures"),
    [
        (
            {"state": "BLOCKED", "instruction_summary": {"findings": 0}},
            {"strict": True},
            False,
            ("blocking-findings",),
        ),
        (
            {"state": "NEEDS ATTENTION", "instruction_summary": {"findings": 2}},
            {"fail_on_integrity": True},
            False,
            ("instruction-integrity-findings",),
        ),
        (
            {"state": "NEEDS ATTENTION", "instruction_summary": {"findings": 0}},
            {"require_ready": True},
            False,
            ("repository-not-ready",),
        ),
        (
            {"state": "READY", "instruction_summary": {"findings": 0}},
            {"strict": True, "fail_on_integrity": True, "require_ready": True},
            True,
            (),
        ),
    ],
)
def test_evaluate_preflight_policy(
    report: dict[str, object],
    options: dict[str, bool],
    expected_passed: bool,
    expected_failures: tuple[str, ...],
) -> None:
    decision = evaluate_preflight_policy(report, **options)

    assert decision.passed is expected_passed
    assert decision.failures == expected_failures
    assert decision.to_dict() == {
        "passed": expected_passed,
        "failures": list(expected_failures),
    }


def test_preflight_policy_reports_all_enabled_failures() -> None:
    report = {
        "state": "BLOCKED",
        "instruction_summary": {"findings": 3},
    }

    decision = evaluate_preflight_policy(
        report,
        strict=True,
        fail_on_integrity=True,
        require_ready=True,
    )

    assert decision.passed is False
    assert decision.failures == (
        "blocking-findings",
        "instruction-integrity-findings",
        "repository-not-ready",
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_repository_only_preflight_is_independent_of_host_toolchain(
    tmp_path: Path,
    monkeypatch,
) -> None:
    subprocess.run(("git", "-C", str(tmp_path), "init"), check=True, capture_output=True, text=True)
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"packageManager":"pnpm@10","scripts":{"test":"vitest"}}',
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Run §pnpm test§.\n".replace("§", "`"), encoding="utf-8")

    def fail_tool_check(label: str, command: tuple[str, ...]) -> Check:
        raise AssertionError(f"local tool check should not run: {label} {command}")

    monkeypatch.setattr("codex_workspace_bootstrap.audit._tool_check", fail_tool_check)

    report = build_preflight(tmp_path, include_local_toolchain=False)

    assert report["local_toolchain_checked"] is False
    assert report["state"] == "READY"
    assert not {
        "git",
        "python",
        "node",
        "powershell",
        "wsl",
        "codex",
        "npm",
        "pnpm",
        "yarn",
        "bun",
    }.intersection(item["name"] for item in report["checks"])
    assert "**Local toolchain checks:** skipped (repository-only mode)" in render_markdown(report)


def test_next_actions_keeps_package_manager_conflict_high_priority_without_tool_checks() -> None:
    checks = [
        Check(
            "package-manager-evidence",
            "warn",
            "Conflicting Node.js package-manager evidence detected: npm, pnpm",
        ),
    ]

    actions = next_actions(checks, [], ["Node.js"])

    assert any(
        item.priority == "P1"
        and item.title == "Resolve conflicting repository package-manager evidence"
        for item in actions
    )
