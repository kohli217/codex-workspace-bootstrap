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


@dataclass(frozen=True)
class GitHubCheckResult:
    """GitHub Check Run fields derived from one preflight report."""

    name: str
    conclusion: GitHubCheckConclusion
    title: str
    summary: str
    policy: PolicyDecision

    def to_check_run_fields(self) -> dict[str, object]:
        """Return Check Run fields that a caller can combine with head_sha."""

        return {
            "name": self.name,
            "status": "completed",
            "conclusion": self.conclusion,
            "output": {
                "title": self.title,
                "summary": self.summary,
            },
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
    )
