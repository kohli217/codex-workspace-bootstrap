from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class InstructionSignal:
    tool: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class InstructionFinding:
    kind: str
    severity: str
    message: str
    files: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "message": self.message,
            "files": list(self.files),
            "evidence": list(self.evidence),
        }


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

_COMMAND_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bpython\s+-m\s+pytest(?:\s+[^\n`]+)?", re.I),
    re.compile(r"(?<![\w.-])pytest(?:\s+[^\n`]+)?", re.I),
    re.compile(r"\bpython\s+-m\s+unittest(?:\s+[^\n`]+)?", re.I),
    re.compile(r"\b(?:npm|pnpm|bun)\s+(?:run\s+)?[\w:.-]+(?:\s+[^\n`]+)?", re.I),
    re.compile(r"\byarn\s+[\w:.-]+(?:\s+[^\n`]+)?", re.I),
    re.compile(r"\bgo\s+test(?:\s+[^\n`]+)?", re.I),
    re.compile(r"\bcargo\s+test(?:\s+[^\n`]+)?", re.I),
)

_CODE_FENCE = re.compile(r"```(?:[A-Za-z0-9_+.-]+)?\s*\n(.*?)```", re.S)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_PACKAGE_COMMAND = re.compile(r"^(npm|pnpm|yarn|bun)\b", re.I)
_SCRIPT_COMMAND = re.compile(
    r"^(npm|pnpm|bun)\s+(?:run\s+)?([\w:.-]+)|^yarn\s+(?:run\s+)?([\w:.-]+)",
    re.I,
)


def detect_instruction_signals(root: Path) -> list[InstructionSignal]:
    root = root.resolve()
    found: list[InstructionSignal] = []
    seen: set[tuple[str, str]] = set()

    for tool, relative in EXACT_INSTRUCTION_FILES:
        if (root / relative).is_file():
            key = (tool, relative)
            if key not in seen:
                found.append(InstructionSignal(tool, relative))
                seen.add(key)

    for tool, relative in INSTRUCTION_DIRECTORIES:
        directory = root / relative
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            key = (tool, rel)
            if key not in seen:
                found.append(InstructionSignal(tool, rel))
                seen.add(key)

    return found


def _read_instruction(root: Path, signal: InstructionSignal) -> str:
    path = root / signal.path
    try:
        if path.stat().st_size > 512_000:
            return ""
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _command_regions(text: str) -> list[str]:
    regions = _CODE_FENCE.findall(text)
    regions.extend(_INLINE_CODE.findall(text))
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-*+> ").strip()
        if re.match(
            r"^(?:python\s+-m\s+|pytest\b|npm\b|pnpm\b|yarn\b|bun\b|go\s+test\b|cargo\s+test\b)",
            line,
            re.I,
        ):
            regions.append(line)
    return regions


def extract_commands(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for region in _command_regions(text):
        for pattern in _COMMAND_PATTERNS:
            for match in pattern.finditer(region):
                command = " ".join(match.group(0).strip().split())
                if command and command.lower() not in seen:
                    found.append(command)
                    seen.add(command.lower())
    return found


def _package_json(root: Path) -> dict[str, object]:
    path = root / "package.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _repo_package_managers(root: Path) -> set[str]:
    managers: set[str] = set()
    package = _package_json(root)
    declared = package.get("packageManager")
    if isinstance(declared, str) and declared:
        manager = declared.split("@", 1)[0].strip().lower()
        if manager in {"npm", "pnpm", "yarn", "bun"}:
            managers.add(manager)

    lockfiles = {
        "package-lock.json": "npm",
        "npm-shrinkwrap.json": "npm",
        "pnpm-lock.yaml": "pnpm",
        "yarn.lock": "yarn",
        "bun.lock": "bun",
        "bun.lockb": "bun",
    }
    for filename, manager in lockfiles.items():
        if (root / filename).is_file():
            managers.add(manager)
    return managers


def _script_names(root: Path) -> set[str]:
    scripts = _package_json(root).get("scripts")
    if not isinstance(scripts, dict):
        return set()
    return {
        str(name)
        for name, value in scripts.items()
        if isinstance(name, str) and isinstance(value, str)
    }


def _manager_for_command(command: str) -> str | None:
    match = _PACKAGE_COMMAND.match(command.strip())
    return match.group(1).lower() if match else None


def _script_for_command(command: str) -> tuple[str, str] | None:
    match = _SCRIPT_COMMAND.match(command.strip())
    if not match:
        return None
    manager = (match.group(1) or "yarn").lower()
    script = match.group(2) or match.group(3)
    if not script or script in {"install", "ci", "exec", "dlx"}:
        return None
    return manager, script


def _is_validation_command(command: str) -> bool:
    lowered = command.lower()
    return (
        "pytest" in lowered
        or "unittest" in lowered
        or re.search(r"\b(test|lint|check|build|typecheck|validate|verify)(?=$|\s|:)", lowered) is not None
        or lowered.startswith(("go test", "cargo test"))
    )


def lint_instructions(
    root: Path,
    signals: list[InstructionSignal] | None = None,
) -> list[InstructionFinding]:
    root = root.resolve()
    signals = signals if signals is not None else detect_instruction_signals(root)
    per_file_commands: dict[str, list[str]] = {}

    for signal in signals:
        text = _read_instruction(root, signal)
        per_file_commands[signal.path] = extract_commands(text) if text else []

    findings: list[InstructionFinding] = []
    repo_managers = _repo_package_managers(root)
    scripts = _script_names(root)

    instruction_managers: dict[str, set[str]] = {}
    for path, commands in per_file_commands.items():
        managers = {manager for command in commands if (manager := _manager_for_command(command))}
        if managers:
            instruction_managers[path] = managers

        if len(repo_managers) == 1:
            expected = next(iter(repo_managers))
            wrong = sorted(manager for manager in managers if manager != expected)
            if wrong:
                findings.append(
                    InstructionFinding(
                        "package-manager-mismatch",
                        "warning",
                        f"{path} uses {', '.join(wrong)} but repository evidence selects {expected}.",
                        (path,),
                        tuple(sorted(repo_managers)),
                    )
                )

        if scripts:
            for command in commands:
                parsed = _script_for_command(command)
                if not parsed:
                    continue
                _manager, script = parsed
                if script not in scripts and (
                    script == "test"
                    or command.lower().startswith(("npm run ", "pnpm run ", "bun run ", "yarn run "))
                ):
                    findings.append(
                        InstructionFinding(
                            "missing-package-script",
                            "warning",
                            f"{path} references '{command}', but package.json has no '{script}' script.",
                            (path,),
                            (command,),
                        )
                    )

    manager_sets = {
        manager
        for managers in instruction_managers.values()
        for manager in managers
    }
    if len(manager_sets) > 1:
        findings.append(
            InstructionFinding(
                "package-manager-drift",
                "warning",
                "AI instruction files disagree on the JavaScript package manager.",
                tuple(sorted(instruction_managers)),
                tuple(sorted(manager_sets)),
            )
        )

    validation_by_file = {
        path: {command.lower() for command in commands if _is_validation_command(command)}
        for path, commands in per_file_commands.items()
    }
    validation_by_file = {path: commands for path, commands in validation_by_file.items() if commands}
    if len(validation_by_file) >= 2:
        command_sets = {tuple(sorted(commands)) for commands in validation_by_file.values()}
        if len(command_sets) > 1:
            findings.append(
                InstructionFinding(
                    "validation-command-drift",
                    "warning",
                    "AI instruction files specify different validation command sets.",
                    tuple(sorted(validation_by_file)),
                    tuple(
                        sorted(
                            f"{path}: {', '.join(sorted(commands))}"
                            for path, commands in validation_by_file.items()
                        )
                    ),
                )
            )

    return findings


def finding_summary(findings: list[InstructionFinding]) -> dict[str, int]:
    drift_kinds = {"package-manager-drift", "package-manager-mismatch", "validation-command-drift"}
    invalid_kinds = {"missing-package-script"}
    return {
        "findings": len(findings),
        "drift": sum(item.kind in drift_kinds for item in findings),
        "invalid_commands": sum(item.kind in invalid_kinds for item in findings),
    }
