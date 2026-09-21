from __future__ import annotations

from dataclasses import dataclass

from .audit import Check


@dataclass(frozen=True)
class DoctorFinding:
    name: str
    message: str
    guidance: str
    blocking: bool = False


GUIDANCE: dict[str, str] = {
    "git-repository": "Run this command from the intended repository root and confirm Git is initialized when appropriate.",
    "readme": "Add project setup, validation, and contribution guidance to a README.",
    "license": "For public OSS, add an explicit license after confirming the intended terms.",
    "gitignore": "Add a project-appropriate .gitignore before creating local environments or generated files.",
    "agents": "Run 'codex-workspace-bootstrap init-agents .' and review the generated AGENTS.md.",
    "project-manifest": "Confirm the project type and locate or add its normal manifest.",
    "git": "Verify Git is installed and available on PATH.",
    "python": "Verify Python or the Windows Python launcher is installed and available on PATH.",
    "node": "Verify Node.js is installed and available on PATH when the project requires it.",
    "npm": "Verify npm is installed and available on PATH for this repository.",
    "pnpm": "Verify pnpm is installed and available on PATH for this repository.",
    "yarn": "Verify Yarn is installed and available on PATH for this repository.",
    "bun": "Verify Bun is installed and available on PATH for this repository.",
    "package-manager-evidence": "Confirm the intended Node.js package manager in package.json packageManager or with the repository lockfile.",
    "powershell": "Verify Windows PowerShell or PowerShell is available on PATH.",
    "wsl": "Check WSL status only when the repository workflow requires Linux tooling.",
    "codex": "Verify the Codex CLI is installed and available on PATH when local Codex workflows are intended.",
    "secret-risk-files": "Review the listed filenames and their Git tracking state without exposing file contents.",
}


def doctor_findings(checks: list[Check]) -> list[DoctorFinding]:
    findings: list[DoctorFinding] = []
    for check in checks:
        if check.status == "pass":
            continue
        findings.append(
            DoctorFinding(
                name=check.name,
                message=check.message,
                guidance=GUIDANCE.get(
                    check.name,
                    "Review this finding and confirm the repository's documented setup before making changes.",
                ),
                blocking=check.blocking,
            )
        )
    return findings
