from pathlib import Path
import shutil
import subprocess

import pytest

from codex_workspace_bootstrap.cli import main


def test_init_agents_creates_file(tmp_path: Path) -> None:
    code = main(["init-agents", str(tmp_path)])
    assert code == 0
    assert (tmp_path / "AGENTS.md").exists()


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
