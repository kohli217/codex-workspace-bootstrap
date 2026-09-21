from __future__ import annotations

from typing import Iterable

from . import __version__
from .audit import Check


RULE_HELP: dict[str, str] = {
    "git-repository": "Run the audit from the intended Git repository root when repository-aware checks are needed.",
    "readme": "Add or identify project documentation that explains how contributors should work with the repository.",
    "license": "Add an explicit open-source license when the project is intended for public reuse.",
    "gitignore": "Use ignore rules to keep generated, local, and secret-bearing files out of version control.",
    "agents": "Add or generate AGENTS.md so agent-assisted work has repository-specific instructions.",
    "project-manifest": "Add or identify the project manifest that describes the repository toolchain.",
    "git": "Install Git or make it available on PATH when Git-aware checks are required.",
    "python": "Install Python or make it available on PATH when the repository requires Python.",
    "node": "Install Node.js or make it available on PATH when the repository requires Node.js.",
    "npm": "Install npm or make it available on PATH when the repository requires npm.",
    "powershell": "Install or expose PowerShell when Windows PowerShell workflows are required.",
    "wsl": "Install or configure WSL only when the repository workflow requires it.",
    "codex": "Install or expose the Codex CLI when local Codex command checks are required.",
    "secret-risk-files": "Review risky filenames before publishing or merging. The audit does not read file contents.",
}


def _rule(check: Check) -> dict[str, object]:
    help_text = RULE_HELP.get(
        check.name,
        "Review this repository-readiness finding and update project documentation or tooling as appropriate.",
    )
    return {
        "id": check.name,
        "name": check.name,
        "shortDescription": {"text": f"codex-workspace-bootstrap: {check.name}"},
        "fullDescription": {"text": help_text},
        "help": {"text": help_text},
        "properties": {
            "precision": "high" if check.blocking else "medium",
            "tags": ["codex", "repository-readiness"],
        },
    }


def checks_to_sarif(checks: Iterable[Check]) -> dict[str, object]:
    findings = [check for check in checks if check.status != "pass"]
    rule_ids = sorted({check.name for check in findings})
    rule_by_id = {
        check.name: _rule(check)
        for check in findings
    }

    results: list[dict[str, object]] = []
    for check in findings:
        results.append(
            {
                "ruleId": check.name,
                "level": "error" if check.blocking else "warning",
                "message": {"text": check.message},
                "properties": {
                    "blocking": check.blocking,
                    "source": "codex-workspace-bootstrap",
                },
            }
        )

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "codex-workspace-bootstrap",
                        "informationUri": "https://github.com/kohli217/codex-workspace-bootstrap",
                        "version": __version__,
                        "rules": [rule_by_id[rule_id] for rule_id in rule_ids],
                    }
                },
                "results": results,
            }
        ],
    }
