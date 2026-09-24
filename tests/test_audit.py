from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from codex_workspace_bootstrap.audit import (
    Check,
    _git_tracked_files,
    _tool_check,
    audit_repository,
    summary,
)


@pytest.mark.parametrize("returncode", [0, 1])
def test_tool_check_tolerates_non_locale_output(returncode: int) -> None:
    check = _tool_check(
        "example",
        (
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(b'tool \\xff\\x81'); "
            f"sys.exit({returncode})",
        ),
    )

    assert check.status == ("pass" if returncode == 0 else "warn")
    if returncode == 0:
        assert check.message.startswith("tool ")
    else:
        assert "exit code 1" in check.message


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
    assert by_name["secret-risk-files"].paths == (".env",)
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
    assert by_name["secret-risk-files"].paths == ()
    assert "ignored:" in by_name["secret-risk-files"].message


def test_summary_counts_statuses(tmp_path: Path) -> None:
    checks = audit_repository(tmp_path)
    totals = summary(checks)
    assert totals["passed"] + totals["warnings"] == len(checks)
    assert totals["blocking"] == 0


def test_audit_checks_detected_pnpm_instead_of_assuming_npm(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "package.json").write_text(
        '{"packageManager":"pnpm@10","scripts":{"test":"vitest"}}',
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

    def fake_tool_check(label: str, command: tuple[str, ...]):
        from codex_workspace_bootstrap.audit import Check
        return Check(label, "pass", "available")

    monkeypatch.setattr("codex_workspace_bootstrap.audit._tool_check", fake_tool_check)

    checks = audit_repository(tmp_path)
    names = {check.name for check in checks}

    assert "pnpm" in names
    assert "npm" not in names
    assert "package-manager-evidence" not in names


def test_audit_reports_unconfirmed_node_package_manager(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest"}}',
        encoding="utf-8",
    )

    def fake_tool_check(label: str, command: tuple[str, ...]):
        from codex_workspace_bootstrap.audit import Check
        return Check(label, "pass", "available")

    monkeypatch.setattr("codex_workspace_bootstrap.audit._tool_check", fake_tool_check)

    checks = audit_repository(tmp_path)
    by_name = {check.name: check for check in checks}

    assert by_name["package-manager-evidence"].status == "warn"
    assert "does not confirm" in by_name["package-manager-evidence"].message


def test_secret_risk_scan_works_when_repository_parent_is_named_build(tmp_path: Path) -> None:
    root = tmp_path / "build" / "repo"
    root.mkdir(parents=True)
    (root / ".env").write_text("EXAMPLE=not-a-secret\n", encoding="utf-8")

    checks = audit_repository(root)
    by_name = {check.name: check for check in checks}

    assert by_name["secret-risk-files"].status == "warn"
    assert ".env" in by_name["secret-risk-files"].message


def test_secret_risk_scan_prunes_generated_directories(tmp_path: Path) -> None:
    ignored = tmp_path / "node_modules" / "pkg"
    ignored.mkdir(parents=True)
    (ignored / ".env").write_text("EXAMPLE=dependency-file\n", encoding="utf-8")

    cache = tmp_path / ".pytest_cache"
    cache.mkdir()
    (cache / "credentials.json").write_text("{}", encoding="utf-8")

    checks = audit_repository(tmp_path)
    by_name = {check.name: check for check in checks}

    assert by_name["secret-risk-files"].status == "pass"


def test_audit_reports_conflicting_node_package_manager_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "package.json").write_text(
        '{"packageManager":"pnpm@10","scripts":{"test":"vitest"}}',
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    def fake_tool_check(label: str, command: tuple[str, ...]):
        from codex_workspace_bootstrap.audit import Check
        return Check(label, "pass", "available")

    monkeypatch.setattr("codex_workspace_bootstrap.audit._tool_check", fake_tool_check)

    checks = audit_repository(tmp_path)
    by_name = {check.name: check for check in checks}

    assert by_name["package-manager-evidence"].status == "warn"
    assert "Conflicting" in by_name["package-manager-evidence"].message
    assert "npm" in by_name["package-manager-evidence"].message
    assert "pnpm" in by_name["package-manager-evidence"].message


def test_audit_does_not_accept_symlinked_repository_markers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# demo\n", encoding="utf-8")
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(".venv/\n", encoding="utf-8")
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# agents\n", encoding="utf-8")
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text("[project]\nname='demo'\n", encoding="utf-8")

    symlinked = {readme, gitignore, agents, manifest}
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        if path in symlinked:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    checks = audit_repository(tmp_path)
    by_name = {check.name: check for check in checks}

    assert by_name["readme"].status == "warn"
    assert by_name["gitignore"].status == "warn"
    assert by_name["agents"].status == "warn"
    assert by_name["project-manifest"].status == "warn"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_tracked_risky_file_inside_pruned_directory_is_blocking(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    nested = tmp_path / "node_modules" / "pkg"
    nested.mkdir(parents=True)
    (nested / ".env").write_text("EXAMPLE=tracked\n", encoding="utf-8")
    _git(tmp_path, "add", "-f", "node_modules/pkg/.env")

    checks = audit_repository(tmp_path)
    by_name = {check.name: check for check in checks}

    risk = by_name["secret-risk-files"]
    assert risk.status == "warn"
    assert risk.blocking is True
    assert risk.paths == ("node_modules/pkg/.env",)
    assert "node_modules/pkg/.env" in risk.message
    assert "tracked:" in risk.message


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_tracked_risky_file_inside_dist_is_blocking(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "release.key").write_text("not-a-real-key\n", encoding="utf-8")
    _git(tmp_path, "add", "-f", "dist/release.key")

    checks = audit_repository(tmp_path)
    by_name = {check.name: check for check in checks}

    risk = by_name["secret-risk-files"]
    assert risk.blocking is True
    assert risk.paths == ("dist/release.key",)
    assert "dist/release.key" in risk.message


@pytest.mark.parametrize(
    "filename",
    [
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "demo.sln",
        "demo.csproj",
        "demo.fsproj",
        "demo.vbproj",
    ],
)
def test_audit_recognizes_extended_project_manifests(tmp_path: Path, filename: str) -> None:
    (tmp_path / filename).write_text("marker\n", encoding="utf-8")

    checks = audit_repository(tmp_path)
    by_name = {check.name: check for check in checks}

    assert by_name["project-manifest"].status == "pass"
    assert filename in by_name["project-manifest"].message


@pytest.mark.parametrize(
    "filename",
    [
        ".env.production",
        ".env.development.local",
        ".env.test",
        ".env.staging",
    ],
)
def test_audit_warns_on_environment_specific_secret_risk_files(
    tmp_path: Path,
    filename: str,
) -> None:
    (tmp_path / filename).write_text("TOKEN=not-a-real-secret\n", encoding="utf-8")

    checks = audit_repository(tmp_path)
    by_name = {check.name: check for check in checks}

    risk = by_name["secret-risk-files"]
    assert risk.status == "warn"
    assert filename in risk.message


@pytest.mark.parametrize(
    "filename",
    [
        ".env.example",
        ".env.sample",
        ".env.template",
        ".env.dist",
        ".env.defaults",
    ],
)
def test_audit_does_not_flag_common_env_templates(tmp_path: Path, filename: str) -> None:
    (tmp_path / filename).write_text("TOKEN=replace-me\n", encoding="utf-8")

    checks = audit_repository(tmp_path)
    by_name = {check.name: check for check in checks}

    assert by_name["secret-risk-files"].status == "pass"


def test_git_tracked_files_uses_surrogateescape_for_path_bytes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class Result:
        returncode = 0
        stdout = b"normal.txt\0invalid-\xff.env\0"

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/git")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Result())

    tracked = _git_tracked_files(tmp_path)

    assert tracked is not None
    assert "normal.txt" in tracked
    assert any(name.endswith(".env") for name in tracked)


def test_repository_only_audit_skips_local_toolchain_checks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "package.json").write_text(
        '{"packageManager":"pnpm@10","scripts":{"test":"vitest"}}',
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

    def fail_tool_check(label: str, command: tuple[str, ...]):
        raise AssertionError(f"local tool check should not run: {label} {command}")

    monkeypatch.setattr("codex_workspace_bootstrap.audit._tool_check", fail_tool_check)

    checks = audit_repository(tmp_path, include_local_toolchain=False)
    names = {check.name for check in checks}

    assert names.isdisjoint({"git", "python", "node", "powershell", "wsl", "codex"})
    assert names.isdisjoint({"npm", "pnpm", "yarn", "bun"})
    assert "project-manifest" in names
    assert "secret-risk-files" in names


def test_check_to_dict_only_emits_paths_when_present() -> None:
    without_paths = Check("readme", "warn", "README not found")
    with_paths = Check(
        "secret-risk-files",
        "warn",
        "Tracked risky filename.",
        blocking=True,
        paths=(".env.production",),
    )

    assert "paths" not in without_paths.to_dict()
    assert with_paths.to_dict()["paths"] == [".env.production"]
