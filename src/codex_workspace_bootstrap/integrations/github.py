from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..preflight import (
    PREFLIGHT_REPORT_SCHEMA_VERSION,
    PolicyDecision,
    evaluate_preflight_policy,
    render_markdown,
)


GitHubCheckConclusion = Literal["success", "neutral", "failure"]
MAX_GITHUB_CHECK_ANNOTATIONS = 50


def _annotation_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or normalized.startswith("/"):
        return None
    parts = normalized.split("/")
    if any(part in {"", ".."} for part in parts):
        return None
    if parts[0].endswith(":"):
        return None
    return normalized


def _audit_annotations(report: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Build file-level GitHub annotations from structured audit paths."""

    checks = report.get("checks", [])
    if not isinstance(checks, list):
        return ()

    annotations: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for item in checks:
        if not isinstance(item, dict) or item.get("status") == "pass":
            continue
        paths = item.get("paths", [])
        if not isinstance(paths, list):
            continue

        name = str(item.get("name", "repository-readiness"))
        message = str(item.get("message", "")).strip()
        if not message:
            continue
        level = "failure" if bool(item.get("blocking", False)) else "warning"

        for raw_path in paths:
            path = _annotation_path(raw_path)
            if path is None:
                continue
            key = (name, path, level, message)
            if key in seen:
                continue
            seen.add(key)
            annotations.append(
                {
                    "path": path,
                    "start_line": 1,
                    "end_line": 1,
                    "annotation_level": level,
                    "title": f"CWB: {name}"[:255],
                    "message": message,
                    "raw_details": (
                        "CWB reports this as a file-level repository-readiness finding. "
                        "Line 1 is used only as the GitHub annotation anchor."
                    ),
                }
            )
            if len(annotations) >= MAX_GITHUB_CHECK_ANNOTATIONS:
                return tuple(annotations)

    return tuple(annotations)


def _instruction_annotations(report: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Build conservative file-level GitHub annotations from instruction findings."""

    findings = report.get("instruction_findings", [])
    if not isinstance(findings, list):
        return ()

    annotations: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for item in findings:
        if not isinstance(item, dict):
            continue
        files = item.get("files", [])
        if not isinstance(files, list):
            continue

        kind = str(item.get("kind", "instruction-integrity"))
        message = str(item.get("message", "")).strip()
        if not message:
            continue
        level = "failure" if item.get("severity") == "error" else "warning"

        for raw_path in files:
            path = _annotation_path(raw_path)
            if path is None:
                continue
            key = (kind, path, level, message)
            if key in seen:
                continue
            seen.add(key)
            annotations.append(
                {
                    "path": path,
                    "start_line": 1,
                    "end_line": 1,
                    "annotation_level": level,
                    "title": f"CWB: {kind}"[:255],
                    "message": message,
                    "raw_details": (
                        "CWB currently reports this as a file-level finding. "
                        "Line 1 is used only as the GitHub annotation anchor."
                    ),
                }
            )
            if len(annotations) >= MAX_GITHUB_CHECK_ANNOTATIONS:
                return tuple(annotations)

    return tuple(annotations)


def _github_annotations(report: dict[str, object]) -> tuple[dict[str, object], ...]:
    audit = list(_audit_annotations(report))
    remaining = MAX_GITHUB_CHECK_ANNOTATIONS - len(audit)
    if remaining <= 0:
        return tuple(audit[:MAX_GITHUB_CHECK_ANNOTATIONS])
    instruction = list(_instruction_annotations(report))[:remaining]
    return tuple(audit + instruction)


@dataclass(frozen=True)
class GitHubCheckResult:
    """GitHub Check Run fields derived from one preflight report."""

    name: str
    conclusion: GitHubCheckConclusion
    title: str
    summary: str
    policy: PolicyDecision
    annotations: tuple[dict[str, object], ...] = ()

    def to_check_run_fields(self) -> dict[str, object]:
        """Return Check Run fields that a caller can combine with head_sha."""

        output: dict[str, object] = {
            "title": self.title,
            "summary": self.summary,
        }
        if self.annotations:
            output["annotations"] = [dict(item) for item in self.annotations]

        return {
            "name": self.name,
            "status": "completed",
            "conclusion": self.conclusion,
            "output": output,
        }


def build_github_check(
    report: dict[str, object],
    *,
    strict: bool = True,
    fail_on_integrity: bool = False,
    require_ready: bool = False,
    name: str = "CWB Preflight",
) -> GitHubCheckResult:
    """Map a preflight report to a GitHub Check without making network calls."""

    schema_version = report.get("schema_version")
    if schema_version != PREFLIGHT_REPORT_SCHEMA_VERSION:
        raise ValueError(
            "unsupported preflight schema version: "
            f"{schema_version!r}; expected {PREFLIGHT_REPORT_SCHEMA_VERSION}"
        )

    decision = evaluate_preflight_policy(
        report,
        strict=strict,
        fail_on_integrity=fail_on_integrity,
        require_ready=require_ready,
    )
    state = str(report.get("state", "UNKNOWN"))

    if not decision.passed:
        conclusion: GitHubCheckConclusion = "failure"
    elif state == "READY":
        conclusion = "success"
    else:
        conclusion = "neutral"

    return GitHubCheckResult(
        name=name,
        conclusion=conclusion,
        title=f"CWB preflight: {state}",
        summary=render_markdown(report),
        policy=decision,
        annotations=_github_annotations(report),
    )
