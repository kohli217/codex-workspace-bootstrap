from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import posixpath
import re


@dataclass(frozen=True)
class InstructionSignal:
    tool: str
    path: str
    scope: str = "."
    kind: str = "repository"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class InstructionFinding:
    kind: str
    severity: str
    message: str
    files: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    scope: str = "."

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "message": self.message,
            "files": list(self.files),
            "evidence": list(self.evidence),
            "scope": self.scope,
        }


EXACT_INSTRUCTION_FILES: tuple[tuple[str, str], ...] = (
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
)

_EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "dist",
    "build",
}


def _walk_repository(root: Path):
    """Walk repository content while pruning directories we never inspect."""
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in _EXCLUDED_PARTS]
        yield Path(current), dirnames, filenames

_COMMAND_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:uv|poetry|pdm)\s+run\s+pytest(?:\s+[^\n`]+)?", re.I),
    re.compile(r"\bpython\s+-m\s+pytest(?:\s+[^\n`]+)?", re.I),
    re.compile(r"(?<![\w.-])pytest(?:\s+[^\n`]+)?", re.I),
    re.compile(r"\bpython\s+-m\s+unittest(?:\s+[^\n`]+)?", re.I),
    re.compile(r"\b(?:npm|pnpm|bun)\s+(?:run\s+)?[\w:.-]+(?:\s+[^\n`]+)?", re.I),
    re.compile(r"\byarn\s+(?:run\s+)?[\w:.-]+(?:\s+[^\n`]+)?", re.I),
    re.compile(r"\bgo\s+test(?:\s+[^\n`]+)?", re.I),
    re.compile(r"\bcargo\s+test(?:\s+[^\n`]+)?", re.I),
    re.compile(r"(?<![\w.-])(?:make|just)\s+[\w:.-]+(?:\s+[^\n`]+)?", re.I),
    re.compile(r"(?<![\w.-])(?:\.\/)?gradlew?\s+[\w:.-]+(?:\s+[^\n`]+)?", re.I),
    re.compile(r"(?<![\w.-])(?:\.\/)?mvnw?\s+[\w:.-]+(?:\s+[^\n`]+)?", re.I),
    re.compile(r"\bdotnet\s+test(?:\s+[^\n`]+)?", re.I),
)

_CODE_FENCE = re.compile(r"```(?:[A-Za-z0-9_+.-]+)?\s*\n(.*?)```", re.S)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_PACKAGE_COMMAND = re.compile(r"^(npm|pnpm|yarn|bun)\b", re.I)
_SCRIPT_COMMAND = re.compile(
    r"^(npm|pnpm|bun)\s+(?:run\s+)?([\w:.-]+)|^yarn\s+(?:run\s+)?([\w:.-]+)",
    re.I,
)


def _safe_read(path: Path) -> str:
    try:
        if path.stat().st_size > 512_000:
            return ""
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _frontmatter_value(text: str, keys: tuple[str, ...]) -> str | None:
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None

    lines = parts[1].splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        for key in keys:
            prefix = f"{key}:"
            if not stripped.lower().startswith(prefix.lower()):
                continue

            value = stripped[len(prefix):].strip()
            if value:
                return value

            # Support simple YAML block lists without adding a YAML dependency:
            #
            # globs:
            #   - "src/**/*.ts"
            #   - "tests/**/*.ts"
            items: list[str] = []
            for following in lines[index + 1 :]:
                next_stripped = following.strip()
                if not next_stripped:
                    continue
                if next_stripped.startswith("- "):
                    item = next_stripped[2:].strip()
                    if item:
                        items.append(item)
                    continue
                # A new top-level frontmatter key ends the block list.
                if not following.startswith((" ", "\t")):
                    break
                # Ignore indented content we cannot safely interpret.
            return ", ".join(items) if items else None
    return None


def _split_patterns(value: str) -> list[str]:
    value = value.strip().strip('"').strip("'")
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [
        item.strip().strip('"').strip("'")
        for item in value.split(",")
        if item.strip().strip('"').strip("'")
    ]


def _static_prefix(pattern: str) -> str:
    value = pattern.strip().lstrip("!").removeprefix("./")
    parts: list[str] = []
    for part in value.split("/"):
        if not part:
            continue
        if any(token in part for token in ("*", "?", "[", "{")):
            break
        parts.append(part)
    if not parts:
        return "."
    if "." in parts[-1] and len(parts) > 1:
        parts = parts[:-1]
    return "/".join(parts) if parts else "."


def _scope_metadata(text: str) -> tuple[str, bool]:
    raw = _frontmatter_value(text, ("applyTo", "globs"))
    if not raw:
        return ".", False
    prefixes = [_static_prefix(pattern) for pattern in _split_patterns(raw)]
    prefixes = [prefix for prefix in prefixes if prefix]
    if not prefixes or "." in prefixes:
        return ".", True
    try:
        common = posixpath.commonpath(prefixes)
    except ValueError:
        return ".", True
    return common or ".", True


def _agent_signals(root: Path) -> list[InstructionSignal]:
    by_directory: dict[Path, dict[str, Path]] = {}
    for directory, _dirnames, filenames in _walk_repository(root):
        for filename in filenames:
            if filename not in {"AGENTS.md", "AGENTS.override.md"}:
                continue
            path = directory / filename
            by_directory.setdefault(directory, {})[filename] = path

    found: list[InstructionSignal] = []
    for directory, candidates in sorted(by_directory.items(), key=lambda item: item[0].as_posix()):
        chosen = candidates.get("AGENTS.override.md") or candidates.get("AGENTS.md")
        if chosen is None:
            continue
        rel = chosen.relative_to(root).as_posix()
        scope_path = directory.relative_to(root).as_posix()
        scope = "." if scope_path == "." else scope_path
        kind = "override" if chosen.name == "AGENTS.override.md" else "repository"
        tool = "Codex override" if kind == "override" else "Codex / OpenAI agents"
        found.append(InstructionSignal(tool, rel, scope, kind))
    return found


def _instruction_file_allowed(tool: str, path: Path) -> bool:
    name = path.name.lower()
    if name in {"readme", "readme.md", "readme.txt", "license", "license.md"}:
        return False
    if tool == "GitHub Copilot":
        return name.endswith(".instructions.md")
    if tool == "Cursor":
        return path.suffix.lower() == ".mdc"
    if tool == "Continue":
        return path.suffix.lower() in {".md", ".mdc"}
    if tool == "Cline":
        return path.suffix.lower() in {"", ".md", ".mdc"}
    return True


def _combine_scope(base_scope: str, child_scope: str) -> str:
    if child_scope == ".":
        return base_scope
    if base_scope == ".":
        return child_scope
    return posixpath.join(base_scope, child_scope)


def _cursor_rule_signals(root: Path) -> list[InstructionSignal]:
    found: list[InstructionSignal] = []

    cursor_dirs: list[Path] = []
    for directory, dirnames, _filenames in _walk_repository(root):
        if ".cursor" in dirnames:
            cursor_dirs.append(directory / ".cursor")

    for cursor_dir in sorted(cursor_dirs):
        rules_dir = cursor_dir / "rules"
        if not rules_dir.is_dir():
            continue

        base_dir = cursor_dir.parent
        base_rel = base_dir.relative_to(root).as_posix()
        base_scope = "." if base_rel == "." else base_rel

        for current, dirnames, filenames in os.walk(rules_dir):
            dirnames[:] = [name for name in dirnames if name not in _EXCLUDED_PARTS]
            current_path = Path(current)
            for filename in sorted(filenames):
                path = current_path / filename
                if not _instruction_file_allowed("Cursor", path):
                    continue

                text = _safe_read(path)
                glob_scope, has_glob_scope = _scope_metadata(text)
                always_apply = _frontmatter_value(text, ("alwaysApply",))
                always = bool(always_apply and always_apply.strip().lower() == "true")

                if has_glob_scope:
                    scope = _combine_scope(base_scope, glob_scope)
                    kind = "path-specific"
                elif always:
                    scope = base_scope
                    kind = "repository"
                else:
                    scope = base_scope
                    kind = "conditional"

                found.append(
                    InstructionSignal(
                        "Cursor",
                        path.relative_to(root).as_posix(),
                        scope,
                        kind,
                    )
                )

    return found

def detect_instruction_signals(root: Path) -> list[InstructionSignal]:
    root = root.resolve()
    found: list[InstructionSignal] = []
    seen: set[tuple[str, str]] = set()

    for signal in _agent_signals(root):
        key = (signal.tool, signal.path)
        if key not in seen:
            found.append(signal)
            seen.add(key)

    for signal in _cursor_rule_signals(root):
        key = (signal.tool, signal.path)
        if key not in seen:
            found.append(signal)
            seen.add(key)

    for tool, relative in EXACT_INSTRUCTION_FILES:
        path = root / relative
        if path.is_file():
            key = (tool, relative)
            if key not in seen:
                found.append(InstructionSignal(tool, relative))
                seen.add(key)

    for tool, relative in INSTRUCTION_DIRECTORIES:
        directory = root / relative
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or not _instruction_file_allowed(tool, path):
                continue
            rel = path.relative_to(root).as_posix()
            key = (tool, rel)
            if key in seen:
                continue
            text = _safe_read(path)
            scope, has_scope_metadata = _scope_metadata(text)
            kind = "path-specific" if has_scope_metadata else "repository"
            found.append(InstructionSignal(tool, rel, scope, kind))
            seen.add(key)

    return found


def _read_instruction(root: Path, signal: InstructionSignal) -> str:
    return _safe_read(root / signal.path)


def _command_regions(text: str) -> list[str]:
    regions = _CODE_FENCE.findall(text)
    regions.extend(_INLINE_CODE.findall(text))
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-*+> ").strip()
        if re.match(
            r"^(?:python\s+-m\s+|pytest\b|uv\s+run\s+|poetry\s+run\s+|pdm\s+run\s+|npm\b|pnpm\b|yarn\b|bun\b|go\s+test\b|cargo\s+test\b|make\b|just\b|(?:\.\/)?gradlew?\b|(?:\.\/)?mvnw?\b|dotnet\s+test\b)",
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


def _package_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _scope_directory(root: Path, scope: str) -> Path:
    if scope == ".":
        return root
    candidate = root / scope
    if candidate.suffix and not candidate.is_dir():
        candidate = candidate.parent
    return candidate


def _directory_chain_to_root(root: Path, scope: str) -> list[Path]:
    current = _scope_directory(root, scope)
    if not current.exists():
        current = current.parent if current.parent != current else root
    chain: list[Path] = []
    while True:
        try:
            current.relative_to(root)
        except ValueError:
            break
        chain.append(current)
        if current == root:
            break
        current = current.parent
    return chain


def _package_evidence_at(directory: Path) -> tuple[set[str], set[str]]:
    managers: set[str] = set()
    scripts: set[str] = set()
    package_path = directory / "package.json"
    package = _package_json(package_path)

    declared = package.get("packageManager")
    if isinstance(declared, str) and declared:
        manager = declared.split("@", 1)[0].strip().lower()
        if manager in {"npm", "pnpm", "yarn", "bun"}:
            managers.add(manager)

    raw_scripts = package.get("scripts")
    if isinstance(raw_scripts, dict):
        scripts = {
            str(name)
            for name, value in raw_scripts.items()
            if isinstance(name, str) and isinstance(value, str)
        }

    lockfiles = {
        "package-lock.json": "npm",
        "npm-shrinkwrap.json": "npm",
        "pnpm-lock.yaml": "pnpm",
        "yarn.lock": "yarn",
        "bun.lock": "bun",
        "bun.lockb": "bun",
    }
    for filename, manager in lockfiles.items():
        if (directory / filename).is_file():
            managers.add(manager)

    return managers, scripts


def _repo_package_managers(root: Path, scope: str) -> set[str]:
    for directory in _directory_chain_to_root(root, scope):
        managers, _scripts = _package_evidence_at(directory)
        if managers:
            return managers
    return set()


def _script_names(root: Path, scope: str) -> set[str]:
    for directory in _directory_chain_to_root(root, scope):
        _managers, scripts = _package_evidence_at(directory)
        if scripts or (directory / "package.json").is_file():
            return scripts
    return set()


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


def _validation_key(command: str) -> str | None:
    lowered = " ".join(command.lower().split())
    if "pytest" in lowered:
        return "test:pytest"
    if "unittest" in lowered:
        return "test:unittest"
    if lowered.startswith("go test"):
        return "test:go"
    if lowered.startswith("cargo test"):
        return "test:cargo"
    if lowered.startswith("dotnet test"):
        return "test:dotnet"
    if re.match(r"^(?:\.\/)?gradlew?\s+test\b", lowered):
        return "test:gradle"
    if re.match(r"^(?:\.\/)?mvnw?\s+test\b", lowered):
        return "test:maven"

    task_match = re.match(
        r"^(make|just)\s+(test|lint|check|build|typecheck|validate|verify)(?::[\w.-]+)?\b",
        lowered,
    )
    if task_match:
        return f"{task_match.group(2)}:{task_match.group(1)}"

    parsed = _script_for_command(lowered)
    if not parsed:
        return None
    manager, script = parsed
    family = script.split(":", 1)[0]
    if family in {"test", "lint", "check", "build", "typecheck", "validate", "verify"}:
        return f"{family}:{manager}:{script}"
    return None


def _same_scope_groups(
    signals: list[InstructionSignal],
    values: dict[str, set[str]],
) -> dict[str, dict[str, set[str]]]:
    groups: dict[str, dict[str, set[str]]] = {}
    by_path = {signal.path: signal for signal in signals}
    for path, items in values.items():
        if not items:
            continue
        signal = by_path.get(path)
        if signal is None:
            continue

        # Path-specific rules may share a coarse static prefix while applying
        # to disjoint globs (for example **/*.py vs **/*.ts). Without keeping
        # the full selector semantics, comparing them as peers would create
        # false drift findings. Validate them individually against repository
        # evidence, but exclude them from cross-file drift groups.
        if signal.kind not in {"repository", "override"}:
            continue

        groups.setdefault(signal.scope, {})[path] = items
    return groups


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
    signal_by_path = {signal.path: signal for signal in signals}
    instruction_managers: dict[str, set[str]] = {}

    scope_evidence_checked: set[str] = set()
    for signal in signals:
        if signal.tool == "GitHub Copilot" and signal.path.startswith(".github/instructions/") and signal.kind != "path-specific":
            findings.append(
                InstructionFinding(
                    "missing-scope-metadata",
                    "warning",
                    f"{signal.path} is a Copilot path-specific instruction file but has no applyTo scope metadata.",
                    (signal.path,),
                    (),
                    signal.scope,
                )
            )

        if signal.scope not in scope_evidence_checked:
            repo_managers = _repo_package_managers(root, signal.scope)
            if len(repo_managers) > 1:
                findings.append(
                    InstructionFinding(
                        "package-manager-evidence-conflict",
                        "warning",
                        f"Repository evidence in scope '{signal.scope}' points to multiple JavaScript package managers.",
                        (),
                        tuple(sorted(repo_managers)),
                        signal.scope,
                    )
                )
            scope_evidence_checked.add(signal.scope)

    for path, commands in per_file_commands.items():
        signal = signal_by_path[path]
        managers = {manager for command in commands if (manager := _manager_for_command(command))}
        if managers:
            instruction_managers[path] = managers

        repo_managers = _repo_package_managers(root, signal.scope)
        scripts = _script_names(root, signal.scope)

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
                        signal.scope,
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
                            f"{path} references '{command}', but the nearest package.json for scope '{signal.scope}' has no '{script}' script.",
                            (path,),
                            (command,),
                            signal.scope,
                        )
                    )

    for scope, per_file in _same_scope_groups(signals, instruction_managers).items():
        manager_sets = {manager for managers in per_file.values() for manager in managers}
        if len(manager_sets) > 1:
            findings.append(
                InstructionFinding(
                    "package-manager-drift",
                    "warning",
                    f"AI instruction files in scope '{scope}' disagree on the JavaScript package manager.",
                    tuple(sorted(per_file)),
                    tuple(sorted(manager_sets)),
                    scope,
                )
            )

    validation_by_file = {
        path: {key for command in commands if (key := _validation_key(command))}
        for path, commands in per_file_commands.items()
    }

    for scope, per_file in _same_scope_groups(signals, validation_by_file).items():
        if len(per_file) < 2:
            continue
        families = {"test", "lint", "check", "build", "typecheck", "validate", "verify"}
        conflicting: list[str] = []
        evidence: list[str] = []
        for family in families:
            per_family = {
                path: {key for key in keys if key.startswith(f"{family}:")}
                for path, keys in per_file.items()
            }
            per_family = {path: keys for path, keys in per_family.items() if keys}
            if len(per_family) < 2:
                continue
            shared = set.intersection(*per_family.values())
            if shared:
                continue
            conflicting.append(family)
            evidence.extend(
                f"{path}: {', '.join(sorted(keys))}"
                for path, keys in per_family.items()
            )

        if conflicting:
            findings.append(
                InstructionFinding(
                    "validation-command-drift",
                    "warning",
                    f"AI instruction files in scope '{scope}' disagree on "
                    + ", ".join(sorted(conflicting))
                    + " validation commands.",
                    tuple(sorted(per_file)),
                    tuple(sorted(set(evidence))),
                    scope,
                )
            )

    return findings


def finding_summary(findings: list[InstructionFinding]) -> dict[str, int]:
    drift_kinds = {
        "package-manager-drift",
        "package-manager-mismatch",
        "package-manager-evidence-conflict",
        "validation-command-drift",
    }
    invalid_command_kinds = {"missing-package-script"}
    metadata_kinds = {"missing-scope-metadata"}
    return {
        "findings": len(findings),
        "drift": sum(item.kind in drift_kinds for item in findings),
        "invalid_commands": sum(item.kind in invalid_command_kinds for item in findings),
        "metadata": sum(item.kind in metadata_kinds for item in findings),
    }
