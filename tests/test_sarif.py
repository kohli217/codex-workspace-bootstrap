from codex_workspace_bootstrap.audit import Check
from codex_workspace_bootstrap.sarif import checks_to_sarif, preflight_report_to_sarif


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


def test_preflight_sarif_includes_instruction_integrity_location() -> None:
    payload = preflight_report_to_sarif(
        {
            "checks": [],
            "instruction_findings": [
                {
                    "kind": "package-manager-mismatch",
                    "severity": "warning",
                    "message": "AGENTS.md uses npm but repository evidence selects pnpm.",
                    "files": ["AGENTS.md"],
                    "evidence": ["pnpm"],
                    "scope": ".",
                }
            ],
        }
    )

    result = payload["runs"][0]["results"][0]
    assert result["ruleId"] == "instruction-package-manager-mismatch"
    assert result["level"] == "warning"
    assert result["properties"]["instructionIntegrity"] is True
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "AGENTS.md"


def test_preflight_sarif_combines_audit_and_instruction_rules() -> None:
    payload = preflight_report_to_sarif(
        {
            "checks": [
                {
                    "name": "agents",
                    "status": "warn",
                    "message": "AGENTS.md not found",
                    "blocking": False,
                }
            ],
            "instruction_findings": [
                {
                    "kind": "missing-scope-metadata",
                    "severity": "warning",
                    "message": "Missing applyTo metadata.",
                    "files": [".github/instructions/python.instructions.md"],
                    "evidence": [],
                    "scope": ".",
                }
            ],
        }
    )

    rule_ids = {item["ruleId"] for item in payload["runs"][0]["results"]}
    assert rule_ids == {"agents", "instruction-missing-scope-metadata"}


def test_sarif_has_specific_package_manager_help() -> None:
    payload = checks_to_sarif(
        [
            Check("pnpm", "warn", "pnpm command not found"),
            Check(
                "package-manager-evidence",
                "warn",
                "Conflicting Node.js package-manager evidence detected: npm, pnpm",
            ),
        ]
    )

    rules = {
        rule["id"]: rule
        for rule in payload["runs"][0]["tool"]["driver"]["rules"]
    }

    assert "pnpm" in rules["pnpm"]["help"]["text"].lower()
    assert "packageManager" in rules["package-manager-evidence"]["help"]["text"]
    assert "lockfile" in rules["package-manager-evidence"]["help"]["text"]
