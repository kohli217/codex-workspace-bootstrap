from codex_workspace_bootstrap.audit import Check
from codex_workspace_bootstrap.sarif import checks_to_sarif


def test_sarif_omits_passing_checks() -> None:
    payload = checks_to_sarif(
        [
            Check("readme", "pass", "README detected"),
            Check("agents", "warn", "AGENTS.md not found"),
        ]
    )

    results = payload["runs"][0]["results"]
    assert len(results) == 1
    assert results[0]["ruleId"] == "agents"
    assert results[0]["level"] == "warning"


def test_sarif_marks_blocking_findings_as_error() -> None:
    payload = checks_to_sarif(
        [
            Check(
                "secret-risk-files",
                "warn",
                "Potential secret-bearing filenames detected (tracked: .env). The audit does not read file contents.",
                blocking=True,
            )
        ]
    )

    result = payload["runs"][0]["results"][0]
    assert result["ruleId"] == "secret-risk-files"
    assert result["level"] == "error"
    assert result["properties"]["blocking"] is True


def test_sarif_contains_stable_tool_metadata() -> None:
    payload = checks_to_sarif([Check("agents", "warn", "AGENTS.md not found")])

    assert payload["version"] == "2.1.0"
    driver = payload["runs"][0]["tool"]["driver"]
    assert driver["name"] == "codex-workspace-bootstrap"
    assert driver["informationUri"] == "https://github.com/kohli217/codex-workspace-bootstrap"
    assert driver["rules"][0]["id"] == "agents"
