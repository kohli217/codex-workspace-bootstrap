from pathlib import Path
import shutil
import subprocess

import pytest

from codex_workspace_bootstrap.audit import audit_repository, summary


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ("git", "-C", str(root), *args),
        check=True,
        capture_output=True,
        text=True,
    )


def test_audit_detects_basic_repository_files(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    checks = audit_repository(tmp_path)
    by_name = {c.name: c for c in checks}

    assert by_name["git-repository"].status == "pass"
    assert by_name["readme"].status == "pass"
    assert by_name["license"].status == "pass"
    assert by_name["gitignore"].status == "pass"
    assert by_name["agents"].status == "pass"
    assert by_name["project-manifest"].status == "pass"


def test_audit_warns_on_secret_risk_filename(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("EXAMPLE=not-a-secret\n", encoding="utf-8")
    checks = audit_repository(tmp_path)
    by_name = {c.name: c for c in checks}
    assert by_name["secret-risk-files"].status == "warn"
    assert by_name["secret-risk-files"].blocking is False


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_tracked_secret_risk_file_is_blocking(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    (tmp_path / ".env").write_text("EXAMPLE=not-a-secret\n", encoding="utf-8")
    _git(tmp_path, "add", "-f", ".env")

    checks = audit_repository(tmp_path)
    by_name = {c.name: c for c in checks}

    assert by_name["secret-risk-files"].status == "warn"
    assert by_name["secret-risk-files"].blocking is True
    assert "tracked:" in by_name["secret-risk-files"].message


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_ignored_secret_risk_file_is_not_blocking(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    (tmp_path / ".env").write_text("EXAMPLE=not-a-secret\n", encoding="utf-8")

    checks = audit_repository(tmp_path)
    by_name = {c.name: c for c in checks}

    assert by_name["secret-risk-files"].status == "warn"
    assert by_name["secret-risk-files"].blocking is False
    assert "ignored:" in by_name["secret-risk-files"].message


def test_summary_counts_statuses(tmp_path: Path) -> None:
    checks = audit_repository(tmp_path)
    totals = summary(checks)
    assert totals["passed"] + totals["warnings"] == len(checks)
    assert totals["blocking"] == 0
