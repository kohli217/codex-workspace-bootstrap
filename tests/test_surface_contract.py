from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from codex_workspace_bootstrap.cli import main
from codex_workspace_bootstrap.integrations.github import build_github_check
from codex_workspace_bootstrap.integrations.github_app_service import (
    build_github_app_check,
)
from codex_workspace_bootstrap.preflight import (
    PREFLIGHT_REPORT_SCHEMA_VERSION,
    build_preflight,
)


ROOT = Path(__file__).resolve().parents[1]


def _ready_repository(root: Path) -> None:
    subprocess.run(
        ("git", "-C", str(root), "init", "-q"),
        check=True,
        capture_output=True,
        text=True,
    )
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    (root / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    (root / "package.json").write_text(
        '{"packageManager":"pnpm@10","scripts":{"test":"vitest"}}',
        encoding="utf-8",
    )
    (root / "pnpm-lock.yaml").write_text(
        "lockfileVersion: '9.0'\n",
        encoding="utf-8",
    )
    tick = chr(96)
    (root / "AGENTS.md").write_text(
        f"Validate with {tick}pnpm test{tick}.\n",
        encoding="utf-8",
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_cli_repository_only_json_matches_shared_preflight_contract(
    tmp_path: Path,
) -> None:
    _ready_repository(tmp_path)
    output = tmp_path / "preflight.json"

    direct = build_preflight(
        tmp_path,
        include_local_toolchain=False,
    )
    code = main(
        [
            "preflight",
            str(tmp_path),
            "--repository-only",
            "--json",
            str(output),
        ]
    )
    cli_report = json.loads(output.read_text(encoding="utf-8"))

    assert code == 0
    assert direct == cli_report
    assert direct["schema_version"] == PREFLIGHT_REPORT_SCHEMA_VERSION
    assert direct["local_toolchain_checked"] is False


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_github_app_uses_same_report_to_check_mapping(
    tmp_path: Path,
) -> None:
    _ready_repository(tmp_path)

    report = build_preflight(
        tmp_path,
        include_local_toolchain=False,
    )
    shared = build_github_check(report)
    app = build_github_app_check(tmp_path)

    assert app == shared
    assert app.to_check_run_fields() == shared.to_check_run_fields()


def test_reusable_action_delegates_to_cli_preflight_contract() -> None:
    action = (ROOT / "action.yml").read_text(encoding="utf-8")

    assert 'json_report="$RUNNER_TEMP/cwb-preflight.json"' in action
    assert 'preflight_args=(preflight "$CWB_TARGET_PATH"' in action
    assert 'cwb "${preflight_args[@]}"' in action
    assert 'report = json.loads(' in action
    assert "build_preflight(" not in action
