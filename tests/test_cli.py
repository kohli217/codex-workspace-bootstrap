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
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()

    code = main(["init-agents", str(tmp_path)])

    assert code == 0
    content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "Python" in content
    assert "python -m pytest" in content


def test_init_agents_generates_node_validation_from_script_names(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"node test.js","lint":"eslint ."}}',
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
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest"}}', encoding="utf-8")
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
    assert "codex-workspace-bootstrap 0.2.0" in capsys.readouterr().out
