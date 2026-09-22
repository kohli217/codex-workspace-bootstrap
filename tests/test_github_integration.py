import pytest

from codex_workspace_bootstrap.integrations.github import build_github_check
from codex_workspace_bootstrap.preflight import PREFLIGHT_REPORT_SCHEMA_VERSION


def _report(state: str, *, findings: int = 0) -> dict[str, object]:
    return {
        "schema_version": PREFLIGHT_REPORT_SCHEMA_VERSION,
        "repository": "/repo",
        "state": state,
        "project_signals": [],
        "instruction_signals": [],
        "instruction_findings": [],
        "instruction_summary": {
            "findings": findings,
            "drift": 0,
            "invalid_commands": 0,
            "metadata": 0,
        },
        "summary": {
            "passed": 1,
            "warnings": 0,
            "blocking": 1 if state == "BLOCKED" else 0,
        },
        "next_actions": [],
        "checks": [],
    }


def test_ready_report_maps_to_success_check() -> None:
    check = build_github_check(_report("READY"))

    assert check.conclusion == "success"
    assert check.policy.passed is True
    fields = check.to_check_run_fields()
    assert fields["name"] == "CWB Preflight"
    assert fields["status"] == "completed"
    assert fields["conclusion"] == "success"
    assert "head_sha" not in fields
    output = fields["output"]
    assert isinstance(output, dict)
    assert output["title"] == "CWB preflight: READY"
    assert output["summary"].startswith("# AI Repository Preflight")


def test_needs_attention_is_neutral_when_policy_allows_it() -> None:
    check = build_github_check(_report("NEEDS ATTENTION"))

    assert check.conclusion == "neutral"
    assert check.policy.passed is True


def test_blocked_report_fails_default_strict_policy() -> None:
    check = build_github_check(_report("BLOCKED"))

    assert check.conclusion == "failure"
    assert check.policy.failures == ("blocking-findings",)


def test_require_ready_turns_needs_attention_into_failure() -> None:
    check = build_github_check(
        _report("NEEDS ATTENTION"),
        require_ready=True,
    )

    assert check.conclusion == "failure"
    assert check.policy.failures == ("repository-not-ready",)


def test_fail_on_integrity_turns_integrity_findings_into_failure() -> None:
    check = build_github_check(
        _report("NEEDS ATTENTION", findings=2),
        fail_on_integrity=True,
    )

    assert check.conclusion == "failure"
    assert check.policy.failures == ("instruction-integrity-findings",)


@pytest.mark.parametrize("schema_version", [None, 0, 2, "1"])
def test_github_check_rejects_unsupported_schema(schema_version: object) -> None:
    report = _report("READY")
    report["schema_version"] = schema_version

    with pytest.raises(ValueError, match="unsupported preflight schema version"):
        build_github_check(report)


def test_custom_check_name_is_preserved() -> None:
    check = build_github_check(_report("READY"), name="Repository readiness")

    assert check.name == "Repository readiness"
    assert check.to_check_run_fields()["name"] == "Repository readiness"
