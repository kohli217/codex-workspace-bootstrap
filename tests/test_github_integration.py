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
    assert "annotations" not in output


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


def test_instruction_findings_become_file_level_annotations() -> None:
    report = _report("NEEDS ATTENTION", findings=1)
    report["instruction_findings"] = [
        {
            "kind": "missing-package-script",
            "severity": "warning",
            "message": "Instruction references a missing lint script.",
            "files": ["AGENTS.md", ".github\\instructions\\frontend.md"],
            "evidence": ["npm run lint"],
            "scope": ".",
        }
    ]

    output = build_github_check(report).to_check_run_fields()["output"]
    assert isinstance(output, dict)
    annotations = output["annotations"]
    assert isinstance(annotations, list)
    assert [item["path"] for item in annotations] == [
        "AGENTS.md",
        ".github/instructions/frontend.md",
    ]
    assert all(item["annotation_level"] == "warning" for item in annotations)
    assert all(item["start_line"] == 1 for item in annotations)
    assert all(item["end_line"] == 1 for item in annotations)
    assert all("file-level finding" in item["raw_details"] for item in annotations)


def test_github_annotations_skip_unsafe_paths_and_deduplicate() -> None:
    report = _report("NEEDS ATTENTION", findings=1)
    report["instruction_findings"] = [
        {
            "kind": "package-manager-mismatch",
            "severity": "warning",
            "message": "Package manager mismatch.",
            "files": [
                "./AGENTS.md",
                "AGENTS.md",
                "../outside.md",
                "/absolute.md",
                "C:\\absolute.md",
            ],
            "evidence": ["pnpm"],
            "scope": ".",
        }
    ]

    output = build_github_check(report).to_check_run_fields()["output"]
    assert isinstance(output, dict)
    annotations = output["annotations"]
    assert isinstance(annotations, list)
    assert len(annotations) == 1
    assert annotations[0]["path"] == "AGENTS.md"


def test_github_annotations_are_capped_at_fifty() -> None:
    report = _report("NEEDS ATTENTION", findings=1)
    report["instruction_findings"] = [
        {
            "kind": "validation-command-drift",
            "severity": "warning",
            "message": "Validation commands disagree.",
            "files": [f"rules/rule-{index}.md" for index in range(60)],
            "evidence": [],
            "scope": ".",
        }
    ]

    output = build_github_check(report).to_check_run_fields()["output"]
    assert isinstance(output, dict)
    annotations = output["annotations"]
    assert isinstance(annotations, list)
    assert len(annotations) == 50
    assert annotations[0]["path"] == "rules/rule-0.md"
    assert annotations[-1]["path"] == "rules/rule-49.md"


def test_blocking_audit_paths_become_failure_annotations() -> None:
    report = _report("BLOCKED")
    report["checks"] = [
        {
            "name": "secret-risk-files",
            "status": "warn",
            "message": "Tracked risky filename detected; contents were not read.",
            "blocking": True,
            "paths": [".env.production"],
        }
    ]

    output = build_github_check(report).to_check_run_fields()["output"]
    assert isinstance(output, dict)
    annotations = output["annotations"]
    assert isinstance(annotations, list)
    assert len(annotations) == 1
    assert annotations[0]["path"] == ".env.production"
    assert annotations[0]["annotation_level"] == "failure"
    assert annotations[0]["title"] == "CWB: secret-risk-files"
    assert "repository-readiness finding" in annotations[0]["raw_details"]



def test_applied_repository_suppression_is_visible_in_github_check() -> None:
    report = _report("READY")
    report["configuration"] = {
        "path": ".cwb.json",
        "version": 1,
        "valid": True,
    }
    report["suppressions"] = [
        {
            "target": "check",
            "name": "license",
            "reason": "Intentional internal repository policy.",
            "applied": True,
        }
    ]

    fields = build_github_check(report).to_check_run_fields()
    output = fields["output"]
    assert isinstance(output, dict)
    assert output["title"] == "CWB preflight: READY (1 suppression)"
    annotations = output["annotations"]
    assert isinstance(annotations, list)
    assert len(annotations) == 1
    assert annotations[0]["path"] == ".cwb.json"
    assert annotations[0]["annotation_level"] == "notice"
    assert "repository suppressions applied" in annotations[0]["title"].lower()


def test_invalid_repository_config_is_annotated_in_github_check() -> None:
    report = _report("NEEDS ATTENTION")
    report["configuration"] = {
        "path": ".cwb.json",
        "valid": False,
        "error": "version must be 1",
    }
    report["suppressions"] = []

    output = build_github_check(report).to_check_run_fields()["output"]
    assert isinstance(output, dict)
    annotations = output["annotations"]
    assert isinstance(annotations, list)
    assert len(annotations) == 1
    assert annotations[0]["path"] == ".cwb.json"
    assert annotations[0]["annotation_level"] == "warning"
    assert "version must be 1" in annotations[0]["message"]
