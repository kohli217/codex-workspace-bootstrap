from pathlib import Path
import shutil
import subprocess

import pytest

from codex_workspace_bootstrap.cli import main


def test_init_agents_creates_file(tmp_path: Path) -> None:
    code = main(["init-agents", str(tmp_path)])
    assert code == 0
    content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "No common Python or Node.js manifest detected" in content


def test_init_agents_generates_python_validation(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='demo'\n[project.optional-dependencies]\ntest=['pytest']\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()

    code = main(["init-agents", str(tmp_path)])

    assert code == 0
    content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "Python" in content
    assert "python -m pytest" in content
    assert "pytest configuration or dependency detected" in content


def test_init_agents_generates_node_validation_from_script_names(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"packageManager":"npm@11","scripts":{"test":"node test.js","lint":"eslint ."}}',
        encoding="utf-8",
    )

    code = main(["init-agents", str(tmp_path)])

    assert code == 0
    content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "Node.js" in content
    assert "npm test" in content
    assert "npm run lint" in content
    assert "node test.js" not in content


def test_init_agents_generates_mixed_project_signals(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='demo'\n[tool.pytest.ini_options]\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{"packageManager":"npm@11","scripts":{"test":"vitest"}}',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()

    code = main(["init-agents", str(tmp_path)])

    assert code == 0
    content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "Python, Node.js" in content
    assert "python -m pytest" in content
    assert "npm test" in content


def test_init_agents_does_not_overwrite_without_force(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("keep me", encoding="utf-8")
    code = main(["init-agents", str(tmp_path)])
    assert code == 1
    assert target.read_text(encoding="utf-8") == "keep me"


def test_audit_writes_json(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    code = main(["audit", str(tmp_path), "--json", str(report)])
    assert code == 0
    assert report.exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_strict_mode_fails_for_tracked_secret_risk_file(tmp_path: Path) -> None:
    subprocess.run(("git", "-C", str(tmp_path), "init"), check=True, capture_output=True, text=True)
    (tmp_path / ".env").write_text("EXAMPLE=not-a-secret\n", encoding="utf-8")
    subprocess.run(
        ("git", "-C", str(tmp_path), "add", "-f", ".env"),
        check=True,
        capture_output=True,
        text=True,
    )

    code = main(["audit", str(tmp_path), "--strict"])
    assert code == 1


def test_version_flag_reports_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert "codex-workspace-bootstrap 0.6.0" in capsys.readouterr().out


def test_audit_writes_sarif(tmp_path: Path) -> None:
    import json

    report = tmp_path / "report.sarif"
    code = main(["audit", str(tmp_path), "--sarif", str(report)])

    assert code == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["version"] == "2.1.0"
    assert payload["runs"][0]["tool"]["driver"]["name"] == "codex-workspace-bootstrap"


def test_init_agents_marks_unconfirmed_pytest_for_review(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()

    code = main(["init-agents", str(tmp_path)])

    assert code == 0
    content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "python -m compileall ." in content
    assert "Review-required suggestions" in content
    assert "pytest was not confirmed" in content


def test_init_agents_uses_readme_pytest_evidence(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "README.md").write_text(
        "# Demo\n\nRun tests with:\n\n    python -m pytest\n",
        encoding="utf-8",
    )

    code = main(["init-agents", str(tmp_path)])

    assert code == 0
    content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "python -m pytest" in content
    assert "documented in README" in content
    assert "Review-required suggestions" not in content


def test_preflight_writes_markdown(tmp_path: Path) -> None:
    report = tmp_path / "preflight.md"

    code = main(["preflight", str(tmp_path), "--markdown", str(report)])

    assert code == 0
    assert report.exists()
    content = report.read_text(encoding="utf-8")
    assert "# AI Repository Preflight" in content
    assert "**State:**" in content


def test_preflight_strict_fails_only_on_blocking(tmp_path: Path) -> None:
    code = main(["preflight", str(tmp_path), "--strict"])
    assert code == 0


def test_preflight_fail_on_integrity_returns_nonzero_for_integrity_finding(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"packageManager":"pnpm@10","scripts":{"test":"vitest"}}',
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Run §npm test§.\n".replace("§", "`"), encoding="utf-8")

    code = main(["preflight", str(tmp_path), "--fail-on-integrity"])

    assert code == 1


def test_preflight_writes_comprehensive_sarif(tmp_path: Path) -> None:
    import json

    (tmp_path / "package.json").write_text(
        '{"packageManager":"pnpm@10","scripts":{"test":"vitest"}}',
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Run §npm test§.\n".replace("§", "`"), encoding="utf-8")
    report = tmp_path / "preflight.sarif"

    code = main(["preflight", str(tmp_path), "--sarif", str(report)])

    assert code == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    rule_ids = {item["ruleId"] for item in payload["runs"][0]["results"]}
    assert "instruction-package-manager-mismatch" in rule_ids


def test_init_agents_uses_pnpm_when_repository_evidence_selects_pnpm(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"packageManager":"pnpm@10","scripts":{"test":"vitest","lint":"eslint ."}}',
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

    code = main(["init-agents", str(tmp_path)])

    assert code == 0
    content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "pnpm run test" in content
    assert "pnpm run lint" in content
    assert "npm test" not in content
    assert "repository evidence selects pnpm" in content


def test_init_agents_marks_node_commands_for_review_without_manager_evidence(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest","lint":"eslint ."}}',
        encoding="utf-8",
    )

    code = main(["init-agents", str(tmp_path)])

    assert code == 0
    content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "Review-required suggestions" in content
    assert "npm test" in content
    assert "npm run lint" in content
    assert "package manager is not confirmed" in content


def test_init_agents_avoids_manager_specific_commands_when_evidence_conflicts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"packageManager":"pnpm@10","scripts":{"test":"vitest","lint":"eslint ."}}',
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    code = main(["init-agents", str(tmp_path)])

    assert code == 0
    content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "npm test" not in content
    assert "pnpm run test" not in content
    assert "npm run lint" not in content
    assert "pnpm run lint" not in content


def test_init_agents_refuses_symlink_target_even_with_force(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "AGENTS.md"
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        if path == target:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    code = main(["init-agents", str(tmp_path), "--force"])

    assert code == 1
    assert "refusing to write through symlink" in capsys.readouterr().err
    assert not target.exists()
