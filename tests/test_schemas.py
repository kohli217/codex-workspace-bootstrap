from __future__ import annotations

import json
from pathlib import Path

from codex_workspace_bootstrap.config import (
    CONFIG_VERSION,
    UNSUPPRESSIBLE_CHECKS,
    load_repository_config,
)
from codex_workspace_bootstrap.preflight import (
    PREFLIGHT_REPORT_SCHEMA_VERSION,
    build_preflight,
)
from codex_workspace_bootstrap.schemas import (
    PREFLIGHT_REPORT_JSON_SCHEMA,
    REPOSITORY_CONFIG_JSON_SCHEMA,
    schema_document,
)


def _matches_type(value: object, expected: object) -> bool:
    names = expected if isinstance(expected, list) else [expected]
    for name in names:
        if name == "object" and isinstance(value, dict):
            return True
        if name == "array" and isinstance(value, list):
            return True
        if name == "string" and isinstance(value, str):
            return True
        if name == "boolean" and isinstance(value, bool):
            return True
        if name == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if name == "null" and value is None:
            return True
    return False


def _assert_contract_shape(value: object, schema: dict[str, object]) -> None:
    if "const" in schema:
        assert value == schema["const"]
    if "enum" in schema:
        assert value in schema["enum"]

    if "oneOf" in schema:
        candidates = schema["oneOf"]
        assert isinstance(candidates, list)
        failures = 0
        for candidate in candidates:
            try:
                assert isinstance(candidate, dict)
                _assert_contract_shape(value, candidate)
            except AssertionError:
                failures += 1
        assert failures == len(candidates) - 1
        return

    expected_type = schema.get("type")
    if expected_type is not None:
        assert _matches_type(value, expected_type), (
            f"value {value!r} does not match schema type {expected_type!r}"
        )

    if isinstance(value, dict):
        required = schema.get("required", [])
        assert isinstance(required, list)
        for key in required:
            assert key in value

        properties = schema.get("properties", {})
        assert isinstance(properties, dict)
        for key, item in value.items():
            child = properties.get(key)
            if child is None:
                assert schema.get("additionalProperties", True) is not False
                continue
            assert isinstance(child, dict)
            _assert_contract_shape(item, child)

    if isinstance(value, list):
        child = schema.get("items")
        if isinstance(child, dict):
            for item in value:
                _assert_contract_shape(item, child)


def _ready_repository(root: Path) -> None:
    (root / ".git").mkdir()
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    (root / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname='demo'\nversion='0.0.0'\n",
        encoding="utf-8",
    )
    (root / "AGENTS.md").write_text(
        "Validate with `python -m compileall .`.\n",
        encoding="utf-8",
    )


def test_preflight_schema_version_matches_runtime_contract() -> None:
    version = PREFLIGHT_REPORT_JSON_SCHEMA["properties"]["schema_version"]["const"]
    assert version == PREFLIGHT_REPORT_SCHEMA_VERSION


def test_config_schema_version_matches_runtime_contract() -> None:
    version = REPOSITORY_CONFIG_JSON_SCHEMA["properties"]["version"]["const"]
    assert version == CONFIG_VERSION


def test_config_schema_documents_unsuppressible_checks() -> None:
    checks = (
        REPOSITORY_CONFIG_JSON_SCHEMA["properties"]["suppress"]["properties"]["checks"]
        ["items"]["properties"]["name"]["not"]["enum"]
    )
    assert set(checks) == set(UNSUPPRESSIBLE_CHECKS)


def test_schema_document_returns_an_independent_copy() -> None:
    first = schema_document("preflight")
    second = schema_document("preflight")

    first["title"] = "changed"

    assert second["title"] == "CWB preflight report v1"


def test_representative_preflight_matches_documented_v1_shape(
    tmp_path: Path,
) -> None:
    _ready_repository(tmp_path)

    report = build_preflight(tmp_path, include_local_toolchain=False)

    _assert_contract_shape(report, schema_document("preflight"))


def test_representative_config_matches_documented_v1_shape(
    tmp_path: Path,
) -> None:
    payload = {
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
                    "reason": "Intentional compatibility workflow.",
                }
            ],
        },
    }
    (tmp_path / ".cwb.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    _assert_contract_shape(payload, schema_document("config"))
    parsed = load_repository_config(tmp_path)

    assert parsed is not None
    assert parsed.version == CONFIG_VERSION


def test_preflight_schema_allows_additive_optional_top_level_fields() -> None:
    schema = schema_document("preflight")

    assert schema["additionalProperties"] is True


def test_config_schema_rejects_unknown_top_level_fields_by_contract() -> None:
    schema = schema_document("config")

    assert schema["additionalProperties"] is False
