from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from .audit import Check
from .instructions import InstructionFinding


CONFIG_FILENAME = ".cwb.json"
CONFIG_VERSION = 1
MAX_CONFIG_BYTES = 64_000

UNSUPPRESSIBLE_CHECKS = frozenset(
    {
        "configuration",
        "git-repository",
        "readme",
        "gitignore",
        "project-manifest",
        "secret-risk-files",
    }
)


class RepositoryConfigError(ValueError):
    """Raised when repository-level CWB configuration is unsafe or invalid."""


@dataclass(frozen=True)
class CheckSuppression:
    name: str
    reason: str


@dataclass(frozen=True)
class InstructionSuppression:
    kind: str
    path: str
    scope: str
    reason: str


@dataclass(frozen=True)
class RepositoryConfig:
    path: str
    version: int
    check_suppressions: tuple[CheckSuppression, ...]
    instruction_suppressions: tuple[InstructionSuppression, ...]


@dataclass(frozen=True)
class SuppressionRecord:
    target: str
    reason: str
    applied: bool
    name: str | None = None
    kind: str | None = None
    path: str | None = None
    scope: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "target": self.target,
            "reason": self.reason,
            "applied": self.applied,
        }
        if self.name is not None:
            payload["name"] = self.name
        if self.kind is not None:
            payload["kind"] = self.kind
        if self.path is not None:
            payload["path"] = self.path
        if self.scope is not None:
            payload["scope"] = self.scope
        return payload


def _require_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RepositoryConfigError(f"{label} must be a JSON object")
    return value


def _require_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise RepositoryConfigError(f"{label} must be a JSON array")
    return value


def _require_nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RepositoryConfigError(f"{label} must be a non-empty string")
    return value.strip()


def _reject_unknown_keys(
    value: dict[str, object],
    allowed: set[str],
    label: str,
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise RepositoryConfigError(
            f"{label} contains unsupported key(s): {', '.join(unknown)}"
        )


def _normalize_repo_path(value: object, label: str, *, allow_root: bool = False) -> str:
    path = _require_nonempty_string(value, label).replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]

    if allow_root and path == ".":
        return "."

    if (
        not path
        or path.startswith(("/", "~"))
        or re.match(r"^[A-Za-z]:/", path)
        or any(token in path for token in ("*", "?", "[", "]", "{", "}"))
    ):
        raise RepositoryConfigError(
            f"{label} must be an exact repository-relative path without wildcards"
        )

    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise RepositoryConfigError(
            f"{label} must not contain empty, current-directory, or parent-directory segments"
        )
    return "/".join(parts)


def load_repository_config(root: Path) -> RepositoryConfig | None:
    """Load the optional root .cwb.json suppression configuration."""

    path = root.resolve() / CONFIG_FILENAME
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise RepositoryConfigError(f"{CONFIG_FILENAME} must be a regular file")

    try:
        size = path.stat().st_size
    except OSError as exc:
        raise RepositoryConfigError(f"could not stat {CONFIG_FILENAME}: {exc}") from exc

    if size > MAX_CONFIG_BYTES:
        raise RepositoryConfigError(
            f"{CONFIG_FILENAME} exceeds the {MAX_CONFIG_BYTES}-byte size limit"
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepositoryConfigError(f"could not parse {CONFIG_FILENAME}: {exc}") from exc

    data = _require_object(raw, CONFIG_FILENAME)
    _reject_unknown_keys(data, {"version", "suppress"}, CONFIG_FILENAME)

    version = data.get("version")
    if isinstance(version, bool) or version != CONFIG_VERSION:
        raise RepositoryConfigError(
            f"{CONFIG_FILENAME} version must be {CONFIG_VERSION}"
        )

    suppress = _require_object(data.get("suppress", {}), "suppress")
    _reject_unknown_keys(
        suppress,
        {"checks", "instruction_findings"},
        "suppress",
    )

    check_entries = _require_list(suppress.get("checks", []), "suppress.checks")
    finding_entries = _require_list(
        suppress.get("instruction_findings", []),
        "suppress.instruction_findings",
    )

    check_suppressions: list[CheckSuppression] = []
    seen_checks: set[str] = set()
    for index, raw_entry in enumerate(check_entries):
        label = f"suppress.checks[{index}]"
        entry = _require_object(raw_entry, label)
        _reject_unknown_keys(entry, {"name", "reason"}, label)
        name = _require_nonempty_string(entry.get("name"), f"{label}.name")
        reason = _require_nonempty_string(entry.get("reason"), f"{label}.reason")
        if name in UNSUPPRESSIBLE_CHECKS:
            raise RepositoryConfigError(
                f"{label}.name cannot suppress safety/readiness check {name!r}"
            )
        if name in seen_checks:
            raise RepositoryConfigError(f"duplicate check suppression for {name!r}")
        seen_checks.add(name)
        check_suppressions.append(CheckSuppression(name=name, reason=reason))

    instruction_suppressions: list[InstructionSuppression] = []
    seen_findings: set[tuple[str, str, str]] = set()
    for index, raw_entry in enumerate(finding_entries):
        label = f"suppress.instruction_findings[{index}]"
        entry = _require_object(raw_entry, label)
        _reject_unknown_keys(entry, {"kind", "path", "scope", "reason"}, label)
        kind = _require_nonempty_string(entry.get("kind"), f"{label}.kind")
        path_value = _normalize_repo_path(entry.get("path"), f"{label}.path")
        scope_value = _normalize_repo_path(
            entry.get("scope", "."),
            f"{label}.scope",
            allow_root=True,
        )
        reason = _require_nonempty_string(entry.get("reason"), f"{label}.reason")
        key = (kind, path_value, scope_value)
        if key in seen_findings:
            raise RepositoryConfigError(
                "duplicate instruction suppression for "
                f"kind={kind!r}, path={path_value!r}, scope={scope_value!r}"
            )
        seen_findings.add(key)
        instruction_suppressions.append(
            InstructionSuppression(
                kind=kind,
                path=path_value,
                scope=scope_value,
                reason=reason,
            )
        )

    return RepositoryConfig(
        path=CONFIG_FILENAME,
        version=CONFIG_VERSION,
        check_suppressions=tuple(check_suppressions),
        instruction_suppressions=tuple(instruction_suppressions),
    )


def apply_repository_config(
    config: RepositoryConfig,
    checks: list[Check],
    findings: list[InstructionFinding],
) -> tuple[list[Check], list[InstructionFinding], list[SuppressionRecord]]:
    """Apply safe suppressions and return active findings plus an audit trail."""

    check_applied = {item.name: False for item in config.check_suppressions}
    active_checks: list[Check] = []
    by_check = {item.name: item for item in config.check_suppressions}

    for check in checks:
        suppression = by_check.get(check.name)
        if (
            suppression is not None
            and check.status != "pass"
            and not check.blocking
            and check.name not in UNSUPPRESSIBLE_CHECKS
        ):
            check_applied[suppression.name] = True
            continue
        active_checks.append(check)

    finding_applied: dict[tuple[str, str, str], bool] = {
        (item.kind, item.path, item.scope): False
        for item in config.instruction_suppressions
    }
    active_findings: list[InstructionFinding] = []

    for finding in findings:
        matched = False
        if finding.severity != "error":
            for suppression in config.instruction_suppressions:
                if (
                    suppression.kind == finding.kind
                    and suppression.scope == finding.scope
                    and suppression.path in finding.files
                ):
                    finding_applied[
                        (suppression.kind, suppression.path, suppression.scope)
                    ] = True
                    matched = True
                    break
        if not matched:
            active_findings.append(finding)

    records: list[SuppressionRecord] = []
    for item in config.check_suppressions:
        records.append(
            SuppressionRecord(
                target="check",
                name=item.name,
                reason=item.reason,
                applied=check_applied[item.name],
            )
        )
    for item in config.instruction_suppressions:
        records.append(
            SuppressionRecord(
                target="instruction_finding",
                kind=item.kind,
                path=item.path,
                scope=item.scope,
                reason=item.reason,
                applied=finding_applied[(item.kind, item.path, item.scope)],
            )
        )

    return active_checks, active_findings, records
