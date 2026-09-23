from __future__ import annotations

from copy import deepcopy

from .config import CONFIG_VERSION, UNSUPPRESSIBLE_CHECKS
from .preflight import PREFLIGHT_REPORT_SCHEMA_VERSION


JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


PREFLIGHT_REPORT_JSON_SCHEMA: dict[str, object] = {
    "$schema": JSON_SCHEMA_DIALECT,
    "$id": "https://github.com/kohli217/codex-workspace-bootstrap/schema/preflight-report-v1",
    "title": "CWB preflight report v1",
    "type": "object",
    "required": [
        "schema_version",
        "repository",
        "local_toolchain_checked",
        "state",
        "project_signals",
        "instruction_signals",
        "instruction_findings",
        "instruction_summary",
        "summary",
        "next_actions",
        "checks",
    ],
    "properties": {
        "schema_version": {"const": PREFLIGHT_REPORT_SCHEMA_VERSION},
        "repository": {"type": "string"},
        "local_toolchain_checked": {"type": "boolean"},
        "state": {"enum": ["READY", "NEEDS ATTENTION", "BLOCKED"]},
        "project_signals": {
            "type": "array",
            "items": {"type": "string"},
        },
        "instruction_signals": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["tool", "path", "scope", "kind"],
                "properties": {
                    "tool": {"type": "string"},
                    "path": {"type": "string"},
                    "scope": {"type": "string"},
                    "kind": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "instruction_findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "kind",
                    "severity",
                    "message",
                    "files",
                    "evidence",
                    "scope",
                ],
                "properties": {
                    "kind": {"type": "string"},
                    "severity": {"enum": ["warning", "error"]},
                    "message": {"type": "string"},
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "scope": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "instruction_summary": {
            "type": "object",
            "required": ["findings", "drift", "invalid_commands", "metadata"],
            "properties": {
                "findings": {"type": "integer", "minimum": 0},
                "drift": {"type": "integer", "minimum": 0},
                "invalid_commands": {"type": "integer", "minimum": 0},
                "metadata": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": True,
        },
        "summary": {
            "type": "object",
            "required": ["passed", "warnings", "blocking"],
            "properties": {
                "passed": {"type": "integer", "minimum": 0},
                "warnings": {"type": "integer", "minimum": 0},
                "blocking": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": True,
        },
        "next_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["priority", "title", "command", "reason"],
                "properties": {
                    "priority": {"type": "string"},
                    "title": {"type": "string"},
                    "command": {"type": ["string", "null"]},
                    "reason": {"type": ["string", "null"]},
                },
                "additionalProperties": False,
            },
        },
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "status", "message", "blocking"],
                "properties": {
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                    "message": {"type": "string"},
                    "blocking": {"type": "boolean"},
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "additionalProperties": False,
            },
        },
        "configuration": {
            "oneOf": [
                {
                    "type": "object",
                    "required": ["path", "version", "valid"],
                    "properties": {
                        "path": {"type": "string"},
                        "version": {"const": CONFIG_VERSION},
                        "valid": {"const": True},
                    },
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "required": ["path", "valid", "error"],
                    "properties": {
                        "path": {"type": "string"},
                        "valid": {"const": False},
                        "error": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            ]
        },
        "suppressions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["target", "reason", "applied"],
                "properties": {
                    "target": {
                        "enum": ["check", "instruction_finding"],
                    },
                    "reason": {"type": "string", "minLength": 1},
                    "applied": {"type": "boolean"},
                    "name": {"type": "string"},
                    "kind": {"type": "string"},
                    "path": {"type": "string"},
                    "scope": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
    # Schema v1 permits additive optional top-level fields. A removal, type
    # change, or semantic break requires PREFLIGHT_REPORT_SCHEMA_VERSION += 1.
    "additionalProperties": True,
}


REPOSITORY_CONFIG_JSON_SCHEMA: dict[str, object] = {
    "$schema": JSON_SCHEMA_DIALECT,
    "$id": "https://github.com/kohli217/codex-workspace-bootstrap/schema/repository-config-v1",
    "title": "CWB repository configuration v1",
    "type": "object",
    "required": ["version"],
    "properties": {
        "version": {"const": CONFIG_VERSION},
        "suppress": {
            "type": "object",
            "properties": {
                "checks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "reason"],
                        "properties": {
                            "name": {
                                "type": "string",
                                "minLength": 1,
                                "not": {
                                    "enum": sorted(UNSUPPRESSIBLE_CHECKS),
                                },
                            },
                            "reason": {
                                "type": "string",
                                "minLength": 1,
                            },
                        },
                        "additionalProperties": False,
                    },
                },
                "instruction_findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["kind", "path", "reason"],
                        "properties": {
                            "kind": {
                                "type": "string",
                                "minLength": 1,
                            },
                            "path": {
                                "type": "string",
                                "minLength": 1,
                            },
                            "scope": {
                                "type": "string",
                                "minLength": 1,
                                "default": ".",
                            },
                            "reason": {
                                "type": "string",
                                "minLength": 1,
                            },
                        },
                        "additionalProperties": False,
                    },
                },
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}


def schema_document(kind: str) -> dict[str, object]:
    """Return a copy of a supported public machine-readable schema."""

    if kind == "preflight":
        return deepcopy(PREFLIGHT_REPORT_JSON_SCHEMA)
    if kind == "config":
        return deepcopy(REPOSITORY_CONFIG_JSON_SCHEMA)
    raise ValueError(f"unsupported schema kind: {kind}")
