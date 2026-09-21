from codex_workspace_bootstrap.audit import Check
from codex_workspace_bootstrap.doctor import doctor_findings


def test_doctor_omits_passing_checks() -> None:
    findings = doctor_findings(
        [
            Check("git", "pass", "git version 2.x"),
            Check("codex", "warn", "codex command not found"),
        ]
    )

    assert len(findings) == 1
    assert findings[0].name == "codex"
    assert "PATH" in findings[0].guidance


def test_doctor_preserves_blocking_status() -> None:
    findings = doctor_findings(
        [
            Check(
                "secret-risk-files",
                "warn",
                "Potential secret-bearing filenames detected.",
                blocking=True,
            )
        ]
    )

    assert findings[0].blocking is True
    assert "without exposing file contents" in findings[0].guidance


def test_doctor_has_repository_guidance() -> None:
    findings = doctor_findings(
        [
            Check("agents", "warn", "AGENTS.md not found"),
            Check("gitignore", "warn", ".gitignore not found"),
        ]
    )

    assert "init-agents" in findings[0].guidance
    assert ".gitignore" in findings[1].guidance
