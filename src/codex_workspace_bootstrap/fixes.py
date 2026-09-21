from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .agents import generate_agents
from .instructions import detect_instruction_signals, lint_instructions


@dataclass(frozen=True)
class FixPlanItem:
    kind: str
    description: str
    apply_supported: bool
    target: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_fix_plan(root: Path) -> list[FixPlanItem]:
    root = root.resolve()
    plan: list[FixPlanItem] = []

    signals = detect_instruction_signals(root)
    findings = lint_instructions(root, signals)

    if not signals:
        plan.append(
            FixPlanItem(
                "create-agents",
                "Create an evidence-based AGENTS.md because no supported AI instruction file was detected.",
                True,
                "AGENTS.md",
            )
        )
    elif not (root / "AGENTS.md").exists():
        plan.append(
            FixPlanItem(
                "create-agents",
                "Create AGENTS.md as a neutral shared instruction baseline; existing tool-specific files remain untouched.",
                True,
                "AGENTS.md",
            )
        )

    for finding in findings:
        plan.append(
            FixPlanItem(
                f"manual-{finding.kind}",
                finding.message,
                False,
                ", ".join(finding.files) if finding.files else None,
            )
        )

    return plan


def apply_fix_plan(root: Path, plan: list[FixPlanItem]) -> list[str]:
    root = root.resolve()
    applied: list[str] = []

    for item in plan:
        if not item.apply_supported:
            continue
        if item.kind == "create-agents":
            target = root / "AGENTS.md"
            if target.exists():
                continue
            target.write_text(generate_agents(root), encoding="utf-8")
            applied.append(str(target))

    return applied
