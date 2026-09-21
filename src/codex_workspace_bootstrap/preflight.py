from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .agents import detect_project_signals
from .audit import Check, audit_repository, summary
from .doctor import doctor_findings


@dataclass(frozen=True)
class InstructionSignal:
    tool: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class NextAction:
    priority: str
    title: str
    command: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


EXACT_INSTRUCTION_FILES: tuple[tuple[str, str], ...] = (
    ("Codex / OpenAI agents", "AGENTS.md"),
    ("GitHub Copilot", ".github/copilot-instructions.md"),
    ("Cline", ".clinerules"),
    ("Claude Code", "CLAUDE.md"),
    ("Gemini CLI", "GEMINI.md"),
    ("Cursor", ".cursorrules"),
)

INSTRUCTION_DIRECTORIES: tuple[tuple[str, str], ...] = (
    ("GitHub Copilot", ".github/instructions"),
    ("Cline", ".clinerules"),
    ("Cline", ".cline/rules"),
    ("Continue", ".continue/rules"),
    ("Cursor", ".cursor/rules"),
)

ESSENTIAL_CHECKS = {
    "git-repository",
    "readme",
    "gitignore",
    "project-manifest",
}


def detect_instruction_signals(root: Path) -> list[InstructionSignal]:
    root = root.resolve()
    found: list[InstructionSignal] = []

    for tool, relative in EXACT_INSTRUCTION_FILES:
        if (root / relative).is_file():
            found.append(InstructionSignal(tool, relative))

    for tool, relative in INSTRUCTION_DIRECTORIES:
        directory = root / relative
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                found.append(InstructionSignal(tool, path.relative_to(root).as_posix()))

    return found


def readiness_state(checks: list[Check], instructions: list[InstructionSignal]) -> str:
    if any(check.blocking for check in checks):
        return "BLOCKED"

    essentials_missing = any(
        check.name in ESSENTIAL_CHECKS and check.status != "pass"
        for check in checks
    )
    if essentials_missing or not instructions:
        return "NEEDS ATTENTION"

    return "READY"


def _check_by_name(checks: list[Check], name: str) -> Check | None:
    return next((check for check in checks if check.name == name), None)


def next_actions(
    checks: list[Check],
    instructions: list[InstructionSignal],
    project_signals: list[str],
) -> list[NextAction]:
    actions: list[NextAction] = []

    for finding in doctor_findings(checks):
        if finding.blocking:
            actions.append(
                NextAction(
                    "P0",
                    f"Resolve blocking finding: {finding.name}",
                    reason=finding.guidance,
                )
            )

    if not instructions:
        actions.append(
            NextAction(
                "P1",
                "Add repository instructions for AI coding agents",
                command="cwb init-agents .",
                reason="No recognized AI-agent instruction file was detected.",
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
        npm = _check_by_name(checks, "npm")
        if npm is not None and npm.status != "pass":
            actions.append(
                NextAction(
                    "P1",
                    "Restore the Node.js/npm toolchain required by this repository",
                    command="npm --version",
                    reason=npm.message,
                )
            )

    return actions


def build_preflight(root: Path) -> dict[str, object]:
    root = root.resolve()
    checks = audit_repository(root)
    instructions = detect_instruction_signals(root)
    projects = detect_project_signals(root)
    totals = summary(checks)
    state = readiness_state(checks, instructions)
    actions = next_actions(checks, instructions, projects)

    return {
        "repository": str(root),
        "state": state,
        "project_signals": projects,
        "instruction_signals": [item.to_dict() for item in instructions],
        "summary": totals,
        "next_actions": [item.to_dict() for item in actions],
        "checks": [check.to_dict() for check in checks],
    }


def render_markdown(report: dict[str, object]) -> str:
    state = str(report["state"])
    projects = report["project_signals"]
    instructions = report["instruction_signals"]
    totals = report["summary"]
    actions = report["next_actions"]

    project_text = ", ".join(str(item) for item in projects) if projects else "Unknown / no common manifest detected"

    lines = [
        "# AI Repository Preflight",
        "",
        f"**State:** {state}",
        "",
        f"**Project signals:** {project_text}",
        f"**Audit:** {totals['passed']} passed · {totals['warnings']} warnings · {totals['blocking']} blocking",
        "",
        "## AI instruction coverage",
        "",
    ]

    if instructions:
        for item in instructions:
            lines.append(f"- **{item['tool']}** — `{item['path']}`")
    else:
        lines.append("- No recognized AI-agent instruction files detected.")

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
