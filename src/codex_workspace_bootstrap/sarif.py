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
    "pnpm": "Install pnpm or make it available on PATH when the repository requires pnpm.",
    "yarn": "Install Yarn or make it available on PATH when the repository requires Yarn.",
    "bun": "Install Bun or make it available on PATH when the repository requires Bun.",
    "package-manager-evidence": "Align packageManager and lockfile evidence so the repository identifies one intended Node.js package manager.",
    "powershell": "Install or expose PowerShell when Windows PowerShell workflows are required.",
    "wsl": "Install or configure WSL only when the repository workflow requires it.",
    "codex": "Install or expose the Codex CLI when local Codex command checks are required.",
    "secret-risk-files": "Review risky filenames before publishing or merging. The audit does not read file contents.",
}

INSTRUCTION_HELP: dict[str, str] = {
    "package-manager-mismatch": (
        "Align executable-looking AI instructions with the package manager selected by repository evidence."
    ),
    "package-manager-drift": (
        "Review same-scope AI instruction files that prescribe different JavaScript package managers."
    ),
    "package-manager-evidence-conflict": (
        "Resolve conflicting package-manager evidence such as a packageManager declaration and a stale lockfile."
    ),
    "validation-command-drift": (
        "Review same-scope AI instructions that prescribe incompatible validation commands for the same command family."
    ),
    "missing-package-script": (
        "Update the instruction or package.json so referenced package scripts actually exist in the relevant scope."
    ),
    "missing-scope-metadata": (
        "Add required path-specific scope metadata such as Copilot applyTo frontmatter."
    ),
}


def _audit_rule(check: Check) -> dict[str, object]:
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


def _instruction_rule(kind: str) -> dict[str, object]:
    rule_id = f"instruction-{kind}"
    help_text = INSTRUCTION_HELP.get(
        kind,
        "Review this AI instruction-integrity finding and reconcile it with repository evidence.",
    )
    return {
        "id": rule_id,
        "name": rule_id,
        "shortDescription": {"text": f"codex-workspace-bootstrap: {kind}"},
        "fullDescription": {"text": help_text},
        "help": {"text": help_text},
        "properties": {
            "precision": "medium",
            "tags": ["ai-instructions", "repository-readiness"],
        },
    }


def _payload(
    rules: list[dict[str, object]],
    results: list[dict[str, object]],
) -> dict[str, object]:
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
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }


def _sarif_locations(paths: object) -> list[dict[str, object]]:
    if not isinstance(paths, (list, tuple)):
        return []

    locations: list[dict[str, object]] = []
    for path in paths:
        if not isinstance(path, str) or not path:
            continue
        locations.append(
            {
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": path.replace("\\", "/"),
                    }
                }
            }
        )
    return locations


def checks_to_sarif(checks: Iterable[Check]) -> dict[str, object]:
    findings = [check for check in checks if check.status != "pass"]
    rule_by_id = {check.name: _audit_rule(check) for check in findings}

    results: list[dict[str, object]] = []
    for check in findings:
        result: dict[str, object] = {
            "ruleId": check.name,
            "level": "error" if check.blocking else "warning",
            "message": {"text": check.message},
            "properties": {
                "blocking": check.blocking,
                "source": "codex-workspace-bootstrap",
            },
        }
        locations = _sarif_locations(check.paths)
        if locations:
            result["locations"] = locations
        results.append(result)

    return _payload(
        [rule_by_id[rule_id] for rule_id in sorted(rule_by_id)],
        results,
    )


def preflight_report_to_sarif(report: dict[str, object]) -> dict[str, object]:
    checks = report.get("checks", [])
    instruction_findings = report.get("instruction_findings", [])

    rules: dict[str, dict[str, object]] = {}
    results: list[dict[str, object]] = []

    if isinstance(checks, list):
        for item in checks:
            if not isinstance(item, dict) or item.get("status") == "pass":
                continue
            name = str(item.get("name", "repository-readiness"))
            raw_paths = item.get("paths", [])
            paths = (
                tuple(
                    path
                    for path in raw_paths
                    if isinstance(path, str) and path
                )
                if isinstance(raw_paths, list)
                else ()
            )
            check = Check(
                name=name,
                status=str(item.get("status", "warn")),
                message=str(item.get("message", "")),
                blocking=bool(item.get("blocking", False)),
                paths=paths,
            )
            rules[name] = _audit_rule(check)
            result: dict[str, object] = {
                "ruleId": name,
                "level": "error" if check.blocking else "warning",
                "message": {"text": check.message},
                "properties": {
                    "blocking": check.blocking,
                    "source": "codex-workspace-bootstrap",
                },
            }
            locations = _sarif_locations(check.paths)
            if locations:
                result["locations"] = locations
            results.append(result)

    if isinstance(instruction_findings, list):
        for item in instruction_findings:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind", "instruction-integrity"))
            rule_id = f"instruction-{kind}"
            rules[rule_id] = _instruction_rule(kind)

            result: dict[str, object] = {
                "ruleId": rule_id,
                "level": "error" if item.get("severity") == "error" else "warning",
                "message": {"text": str(item.get("message", ""))},
                "properties": {
                    "scope": str(item.get("scope", ".")),
                    "source": "codex-workspace-bootstrap",
                    "instructionIntegrity": True,
                },
            }

            locations = _sarif_locations(item.get("files", []))
            if locations:
                result["locations"] = locations

            results.append(result)

    return _payload(
        [rules[rule_id] for rule_id in sorted(rules)],
        results,
    )
