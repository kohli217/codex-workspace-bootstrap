from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .agents import detect_project_signals
from .audit import Check, audit_repository, summary
from .doctor import doctor_findings
from .instructions import (
    InstructionFinding,
    InstructionSignal,
    detect_instruction_signals,
    finding_summary,
    lint_instructions,
)


@dataclass(frozen=True)
class NextAction:
    priority: str
    title: str
    command: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


ESSENTIAL_CHECKS = {
    "git-repository",
    "readme",
    "gitignore",
    "project-manifest",
}


def readiness_state(
    checks: list[Check],
    instructions: list[InstructionSignal],
    instruction_findings: list[InstructionFinding] | None = None,
) -> str:
    if any(check.blocking for check in checks):
        return "BLOCKED"

    essentials_missing = any(
        check.name in ESSENTIAL_CHECKS and check.status != "pass"
        for check in checks
    )
    has_repository_wide = any(
        item.scope == "." and item.kind in {"repository", "override"}
        for item in instructions
    )
    if essentials_missing or not has_repository_wide or instruction_findings:
        return "NEEDS ATTENTION"

    return "READY"


def _check_by_name(checks: list[Check], name: str) -> Check | None:
    return next((check for check in checks if check.name == name), None)


def next_actions(
    checks: list[Check],
    instructions: list[InstructionSignal],
    project_signals: list[str],
    instruction_findings: list[InstructionFinding] | None = None,
) -> list[NextAction]:
    actions: list[NextAction] = []
    instruction_findings = instruction_findings or []

    for finding in instruction_findings:
        priority = "P1" if finding.severity == "warning" else "P2"
        actions.append(
            NextAction(
                priority,
                f"Resolve AI instruction integrity finding: {finding.kind}",
                reason=finding.message,
            )
        )

    for finding in doctor_findings(checks):
        if finding.blocking:
            actions.append(
                NextAction(
                    "P0",
                    f"Resolve blocking finding: {finding.name}",
                    reason=finding.guidance,
                )
            )

    has_repository_wide = any(
        item.scope == "." and item.kind in {"repository", "override"}
        for item in instructions
    )
    if not has_repository_wide:
        actions.append(
            NextAction(
                "P1",
                "Add repository-wide instructions for AI coding agents",
                command="cwb init-agents .",
                reason=(
                    "No recognized AI-agent instruction file was detected."
                    if not instructions
                    else "Only scoped or nested AI instructions were detected; no repository-wide baseline is present."
                ),
            )
        )

    essentials = [
        ("git-repository", "Run from a Git repository root"),
        ("readme", "Add a README with setup and validation commands"),
        ("gitignore", "Add a project-appropriate .gitignore"),
        ("project-manifest", "Add or locate the project manifest"),
    ]
    for name, title in essentials:
        check = _check_by_name(checks, name)
        if check is not None and check.status != "pass":
            actions.append(NextAction("P1", title, reason=check.message))

    codex = _check_by_name(checks, "codex")
    if codex is not None and codex.status != "pass":
        actions.append(
            NextAction(
                "P2",
                "Make the Codex CLI available when local Codex workflows are intended",
                command="codex --version",
                reason=codex.message,
            )
        )

    if "Node.js" in project_signals:
        manager_checks = [
            check
            for check in checks
            if check.name in {"npm", "pnpm", "yarn", "bun"}
        ]
        if len(manager_checks) == 1:
            manager = manager_checks[0]
            if manager.status != "pass":
                actions.append(
                    NextAction(
                        "P1",
                        f"Restore the Node.js/{manager.name} toolchain required by this repository",
                        command=f"{manager.name} --version",
                        reason=manager.message,
                    )
                )
        elif not manager_checks:
            evidence = _check_by_name(checks, "package-manager-evidence")
            if evidence is not None and evidence.status != "pass":
                actions.append(
                    NextAction(
                        "P2",
                        "Confirm the repository package manager",
                        reason=evidence.message,
                    )
                )

    return actions


def build_preflight(root: Path) -> dict[str, object]:
    root = root.resolve()
    checks = audit_repository(root)
    instructions = detect_instruction_signals(root)
    instruction_findings = lint_instructions(root, instructions)
    instruction_totals = finding_summary(instruction_findings)
    projects = detect_project_signals(root)
    totals = summary(checks)
    state = readiness_state(checks, instructions, instruction_findings)
    actions = next_actions(checks, instructions, projects, instruction_findings)

    return {
        "repository": str(root),
        "state": state,
        "project_signals": projects,
        "instruction_signals": [item.to_dict() for item in instructions],
        "instruction_findings": [item.to_dict() for item in instruction_findings],
        "instruction_summary": instruction_totals,
        "summary": totals,
        "next_actions": [item.to_dict() for item in actions],
        "checks": [check.to_dict() for check in checks],
    }


def render_markdown(report: dict[str, object]) -> str:
    state = str(report["state"])
    projects = report["project_signals"]
    instructions = report["instruction_signals"]
    totals = report["summary"]
    instruction_totals = report["instruction_summary"]
    findings = report["instruction_findings"]
    actions = report["next_actions"]

    project_text = ", ".join(str(item) for item in projects) if projects else "Unknown / no common manifest detected"

    lines = [
        "# AI Repository Preflight",
        "",
        f"**State:** {state}",
        "",
        f"**Project signals:** {project_text}",
        f"**Audit:** {totals['passed']} passed · {totals['warnings']} warnings · {totals['blocking']} blocking",
        f"**Instruction integrity:** {instruction_totals['findings']} findings · {instruction_totals['drift']} drift · {instruction_totals['invalid_commands']} invalid commands · {instruction_totals['metadata']} metadata",
        "",
        "## AI instruction coverage",
        "",
    ]

    if instructions:
        for item in instructions:
            scope = item.get("scope", ".")
            lines.append(f"- **{item['tool']}** — `{item['path']}` — scope: `{scope}`")
    else:
        lines.append("- No recognized AI-agent instruction files detected.")

    lines.extend(["", "## Instruction integrity", ""])

    if findings:
        for item in findings:
            files = ", ".join(f"`{path}`" for path in item["files"])
            scope = item.get("scope", ".")
            lines.append(f"- **{item['kind']}** — {item['message']} ({files}) — scope: `{scope}`")
    else:
        lines.append("- No cross-agent instruction drift or invalid package scripts detected.")

    lines.extend(["", "## Next actions", ""])

    if actions:
        for item in actions:
            line = f"- **{item['priority']} · {item['title']}**"
            if item.get("command"):
                line += f" — `{item['command']}`"
            if item.get("reason"):
                line += f" — {item['reason']}"
            lines.append(line)
    else:
        lines.append("- No immediate repository-readiness actions.")

    lines.extend(
        [
            "",
            "> This is a deterministic preflight report. It does not prove the repository is secure.",
            "",
        ]
    )
    return "\n".join(lines)
