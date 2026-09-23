import json
from pathlib import Path

import pytest

from codex_workspace_bootstrap.audit import Check
from codex_workspace_bootstrap.config import (
    CheckSuppression,
    InstructionSuppression,
    RepositoryConfig,
    RepositoryConfigError,
    apply_repository_config,
    load_repository_config,
)
from codex_workspace_bootstrap.instructions import InstructionFinding


def _write_config(root: Path, payload: object) -> None:
    (root / ".cwb.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_missing_repository_config_is_optional(tmp_path: Path) -> None:
    assert load_repository_config(tmp_path) is None


def test_load_repository_config_parses_narrow_suppressions(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        {
            "version": 1,
            "suppress": {
                "checks": [
                    {
                        "name": "license",
                        "reason": "Internal repository.",
                    }
                ],
                "instruction_findings": [
                    {
                        "kind": "validation-command-drift",
                        "path": "CLAUDE.md",
                        "scope": ".",
                        "reason": "Intentional smoke-test split.",
                    }
                ],
            },
        },
    )

    config = load_repository_config(tmp_path)

    assert config is not None
    assert config.version == 1
    assert config.check_suppressions == (
        CheckSuppression("license", "Internal repository."),
    )
    assert config.instruction_suppressions == (
        InstructionSuppression(
            "validation-command-drift",
            "CLAUDE.md",
            ".",
            "Intentional smoke-test split.",
        ),
    )


@pytest.mark.parametrize(
    "name",
    [
        "configuration",
        "git-repository",
        "readme",
        "gitignore",
        "project-manifest",
        "secret-risk-files",
    ],
)
def test_repository_config_rejects_safety_and_essential_check_suppressions(
    tmp_path: Path,
    name: str,
) -> None:
    _write_config(
        tmp_path,
        {
            "version": 1,
            "suppress": {
                "checks": [
                    {
                        "name": name,
                        "reason": "Do not do this.",
                    }
                ]
            },
        },
    )

    with pytest.raises(RepositoryConfigError, match="cannot suppress"):
        load_repository_config(tmp_path)


@pytest.mark.parametrize(
    "path",
    [
        "../AGENTS.md",
        "/tmp/AGENTS.md",
        "C:/repo/AGENTS.md",
        "**/AGENTS.md",
        "rules/*.md",
    ],
)
def test_repository_config_requires_exact_relative_instruction_paths(
    tmp_path: Path,
    path: str,
) -> None:
    _write_config(
        tmp_path,
        {
            "version": 1,
            "suppress": {
                "instruction_findings": [
                    {
                        "kind": "validation-command-drift",
                        "path": path,
                        "reason": "Intentional.",
                    }
                ]
            },
        },
    )

    with pytest.raises(RepositoryConfigError):
        load_repository_config(tmp_path)


def test_repository_config_requires_reason(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        {
            "version": 1,
            "suppress": {
                "checks": [
                    {
                        "name": "license",
                        "reason": "",
                    }
                ]
            },
        },
    )

    with pytest.raises(RepositoryConfigError, match="reason"):
        load_repository_config(tmp_path)


def test_repository_config_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "actual.json"
    target.write_text('{"version": 1}', encoding="utf-8")
    link = tmp_path / ".cwb.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available in this test environment")

    with pytest.raises(RepositoryConfigError, match="non-symlink"):
        load_repository_config(tmp_path)


def test_apply_repository_config_records_applied_and_unused_suppressions() -> None:
    config = RepositoryConfig(
        path=".cwb.json",
        version=1,
        check_suppressions=(
            CheckSuppression("license", "Intentional."),
            CheckSuppression("codex", "CI does not require local Codex."),
        ),
        instruction_suppressions=(
            InstructionSuppression(
                "package-manager-mismatch",
                "AGENTS.md",
                ".",
                "Intentional compatibility command.",
            ),
        ),
    )
    checks = [
        Check("license", "warn", "License file not found"),
        Check("readme", "pass", "README detected"),
    ]
    findings = [
        InstructionFinding(
            "package-manager-mismatch",
            "warning",
            "AGENTS.md uses npm but repository evidence selects pnpm.",
            ("AGENTS.md",),
            ("pnpm",),
            ".",
        )
    ]

    active_checks, active_findings, records = apply_repository_config(
        config,
        checks,
        findings,
    )

    assert [item.name for item in active_checks] == ["readme"]
    assert active_findings == []
    assert [item.applied for item in records] == [True, False, True]


def test_apply_repository_config_never_suppresses_blocking_checks() -> None:
    config = RepositoryConfig(
        path=".cwb.json",
        version=1,
        check_suppressions=(
            CheckSuppression("future-blocking-check", "Attempted exception."),
        ),
        instruction_suppressions=(),
    )
    blocking = Check(
        "future-blocking-check",
        "warn",
        "Blocking condition.",
        blocking=True,
    )

    active_checks, _findings, records = apply_repository_config(
        config,
        [blocking],
        [],
    )

    assert active_checks == [blocking]
    assert records[0].applied is False


def test_apply_repository_config_never_suppresses_error_instruction_findings() -> None:
    config = RepositoryConfig(
        path=".cwb.json",
        version=1,
        check_suppressions=(),
        instruction_suppressions=(
            InstructionSuppression(
                "future-error",
                "AGENTS.md",
                ".",
                "Attempted exception.",
            ),
        ),
    )
    finding = InstructionFinding(
        "future-error",
        "error",
        "Unsafe instruction.",
        ("AGENTS.md",),
        (),
        ".",
    )

    _checks, active_findings, records = apply_repository_config(
        config,
        [],
        [finding],
    )

    assert active_findings == [finding]
    assert records[0].applied is False



@pytest.mark.parametrize("version", [True, 1.0, "1", 2, None])
def test_repository_config_requires_integer_version_one(
    tmp_path: Path,
    version: object,
) -> None:
    _write_config(tmp_path, {"version": version})

    with pytest.raises(RepositoryConfigError, match="version must be 1"):
        load_repository_config(tmp_path)


def test_repository_config_rejects_oversized_file(tmp_path: Path) -> None:
    (tmp_path / ".cwb.json").write_text(" " * 64_001, encoding="utf-8")

    with pytest.raises(RepositoryConfigError, match="size limit"):
        load_repository_config(tmp_path)
