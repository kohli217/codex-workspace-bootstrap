from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import posixpath
import re
import shlex


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
    re.compile(r"\b(?:npm|pnpm|bun)\s+(?:run\s+)?[\w:./=@-]+(?:\s+[^\n`]+)?", re.I),
    re.compile(r"\byarn\s+(?:run\s+)?[\w:./=@-]+(?:\s+[^\n`]+)?", re.I),
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

def _safe_read(path: Path) -> str:
    try:
        if path.is_symlink():
            return ""
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


def _split_top_level_commas(value: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    braces = 0
    brackets = 0
    parens = 0

    for char in value:
        if escaped:
            current.append(char)
            escaped = False
            continue

        if char == "\\":
            current.append(char)
            escaped = True
            continue

        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue

        if char in {"'", '"'}:
            quote = char
            current.append(char)
            continue

        if char == "{":
            braces += 1
        elif char == "}":
            braces = max(0, braces - 1)
        elif char == "[":
            brackets += 1
        elif char == "]":
            brackets = max(0, brackets - 1)
        elif char == "(":
            parens += 1
        elif char == ")":
            parens = max(0, parens - 1)

        if char == "," and braces == 0 and brackets == 0 and parens == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
            continue

        current.append(char)

    item = "".join(current).strip()
    if item:
        items.append(item)
    return items


def _strip_matching_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def _split_patterns(value: str) -> list[str]:
    value = value.strip()

    # Inline YAML arrays are common, but a glob character class such as [ab]
    # is also valid. Only treat brackets as an array when the interior looks
    # list-like.
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if "," in inner or inner.startswith(("'", '"')):
            value = inner

    raw_items = _split_top_level_commas(value)
    patterns: list[str] = []

    for raw in raw_items:
        item = _strip_matching_quotes(raw)
        if not item:
            continue

        # Copilot commonly wraps alternatives in one quoted brace expression:
        # "{src/**/test/**,src/**/*.test.ts}". Expand only a brace that wraps
        # the whole selector; embedded brace expansion stays intact so
        # apps/web/{src,tests}/** still has static prefix apps/web.
        if item.startswith("{") and item.endswith("}"):
            alternatives = [
                _strip_matching_quotes(part)
                for part in _split_top_level_commas(item[1:-1])
            ]
            alternatives = [part for part in alternatives if part]
            if len(alternatives) > 1:
                patterns.extend(alternatives)
                continue

        patterns.append(item)

    return patterns


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
            if path.is_symlink():
                continue
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


def _safe_sibling_instruction_alias(path: Path, target_name: str) -> Path | None:
    if not path.is_symlink():
        return None
    try:
        lexical_target = path.readlink().as_posix()
    except OSError:
        return None

    if lexical_target not in {target_name, f"./{target_name}"}:
        return None

    target = path.parent / target_name
    if target.is_symlink() or not target.is_file():
        return None
    return target


def _hierarchical_named_signals(
    root: Path,
    filename: str,
    tool: str,
) -> list[InstructionSignal]:
    found: list[InstructionSignal] = []
    for directory, _dirnames, filenames in _walk_repository(root):
        if filename not in filenames:
            continue
        path = directory / filename
        if path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        scope_path = directory.relative_to(root).as_posix()
        scope = "." if scope_path == "." else scope_path
        found.append(InstructionSignal(tool, rel, scope, "repository"))
    return found


def _claude_signals(root: Path) -> list[InstructionSignal]:
    found = _hierarchical_named_signals(root, "CLAUDE.md", "Claude Code")

    for directory, _dirnames, filenames in _walk_repository(root):
        if "CLAUDE.md" not in filenames:
            continue
        alias = directory / "CLAUDE.md"
        if _safe_sibling_instruction_alias(alias, "AGENTS.md") is None:
            continue

        rel = alias.relative_to(root).as_posix()
        scope_path = directory.relative_to(root).as_posix()
        scope = "." if scope_path == "." else scope_path
        found.append(InstructionSignal("Claude Code", rel, scope, "alias"))

    return found


def _gemini_context_filenames(root: Path) -> tuple[str, ...]:
    settings_path = root / ".gemini" / "settings.json"
    if not settings_path.is_file() or settings_path.is_symlink():
        return ("GEMINI.md",)

    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ("GEMINI.md",)

    if not isinstance(data, dict):
        return ("GEMINI.md",)

    context = data.get("context")
    if not isinstance(context, dict):
        return ("GEMINI.md",)

    raw = context.get("fileName")
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = [item for item in raw if isinstance(item, str)]
    else:
        return ("GEMINI.md",)

    filenames: list[str] = []
    seen: set[str] = set()
    for value in values:
        name = value.strip()
        if not name:
            continue
        # Gemini documents this setting as a file name. Ignore paths here so
        # repository discovery cannot escape or reinterpret configured roots.
        if Path(name).name != name:
            continue
        if name not in seen:
            filenames.append(name)
            seen.add(name)

    return tuple(filenames) if filenames else ("GEMINI.md",)


def _gemini_signals(root: Path) -> list[InstructionSignal]:
    found: list[InstructionSignal] = []
    for filename in _gemini_context_filenames(root):
        found.extend(_hierarchical_named_signals(root, filename, "Gemini CLI"))
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
                if path.is_symlink() or not _instruction_file_allowed("Cursor", path):
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

    for signal in _claude_signals(root):
        key = (signal.tool, signal.path)
        if key not in seen:
            found.append(signal)
            seen.add(key)

    for signal in _gemini_signals(root):
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
        if path.is_file() and not path.is_symlink():
            key = (tool, relative)
            if key not in seen:
                found.append(InstructionSignal(tool, relative))
                seen.add(key)

    for tool, relative in INSTRUCTION_DIRECTORIES:
        directory = root / relative
        if not directory.is_dir() or directory.is_symlink():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_symlink() or not path.is_file() or not _instruction_file_allowed(tool, path):
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
    path = root / signal.path
    if signal.tool == "Claude Code" and signal.kind == "alias":
        target = _safe_sibling_instruction_alias(path, "AGENTS.md")
        if target is None:
            return ""
        return _safe_read(target)
    return _safe_read(path)


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


def _split_shell_chain(region: str) -> list[str]:
    """Split common shell command chains while respecting simple quotes."""
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0

    while index < len(region):
        char = region[index]

        if escaped:
            current.append(char)
            escaped = False
            index += 1
            continue

        if char == "\\":
            current.append(char)
            escaped = True
            index += 1
            continue

        if quote:
            current.append(char)
            if char == quote:
                quote = None
            index += 1
            continue

        if char in {"'", '"'}:
            quote = char
            current.append(char)
            index += 1
            continue

        if region.startswith("&&", index) or region.startswith("||", index):
            value = "".join(current).strip()
            if value:
                parts.append(value)
            current = []
            index += 2
            continue

        if char in {";", "|"}:
            value = "".join(current).strip()
            if value:
                parts.append(value)
            current = []
            index += 1
            continue

        current.append(char)
        index += 1

    value = "".join(current).strip()
    if value:
        parts.append(value)
    return parts


def extract_commands(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for region in _command_regions(text):
        for segment in _split_shell_chain(region):
            for pattern in _COMMAND_PATTERNS:
                for match in pattern.finditer(segment):
                    command = " ".join(match.group(0).strip().split())
                    if command and command.lower() not in seen:
                        found.append(command)
                        seen.add(command.lower())
    return found


def _package_json(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
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
        candidate = directory / filename
        if candidate.is_file() and not candidate.is_symlink():
            managers.add(manager)

    return managers, scripts


def _repo_package_managers(root: Path, scope: str) -> set[str]:
    for directory in _directory_chain_to_root(root, scope):
        managers, _scripts = _package_evidence_at(directory)
        if managers:
            return managers
    return set()


def _script_names(root: Path, scope: str) -> set[str] | None:
    for directory in _directory_chain_to_root(root, scope):
        package_path = directory / "package.json"
        if package_path.is_file() and not package_path.is_symlink():
            _managers, scripts = _package_evidence_at(directory)
            return scripts
    return None


def _workspace_target_for_command(command: str) -> tuple[bool, str | None]:
    tokens = _package_command_tokens(command.strip())
    if not tokens:
        return False, None

    manager = tokens[0].lower()
    if manager not in {"npm", "pnpm", "yarn", "bun"}:
        return False, None

    if manager == "yarn" and len(tokens) >= 3 and tokens[1] == "workspace":
        return True, tokens[2]

    if manager == "npm":
        targets: list[str] = []
        index = 1
        while index < len(tokens):
            token = tokens[index]
            if token == "--":
                break
            if token in {"--workspace", "-w"}:
                if index + 1 < len(tokens):
                    targets.append(tokens[index + 1])
                else:
                    targets.append("")
                index += 2
                continue
            if token.startswith("--workspace="):
                targets.append(token[len("--workspace="):])
                index += 1
                continue
            if token.startswith("-w="):
                targets.append(token[len("-w="):])
                index += 1
                continue
            index += 1

        if not targets:
            return False, None
        nonempty = [target for target in targets if target]
        if len(nonempty) != 1 or len(targets) != 1:
            return True, None
        return True, nonempty[0]

    target_options = {"--filter", "-F", "--workspace", "-w"}
    target_long_options = {"--filter", "--workspace"}
    directory_options = {"--dir", "-C", "--prefix", "--cwd"}
    directory_long_options = {"--dir", "--prefix", "--cwd"}
    targets: list[str] = []

    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in target_options:
            if index + 1 < len(tokens):
                targets.append(tokens[index + 1])
            else:
                targets.append("")
            index += 2
            continue

        matched_inline = False
        for option in target_long_options:
            prefix = f"{option}="
            if token.startswith(prefix):
                targets.append(token[len(prefix):])
                matched_inline = True
                break
        if matched_inline:
            index += 1
            continue

        if token in directory_options:
            index += 2
            continue
        if any(token.startswith(f"{option}=") for option in directory_long_options):
            index += 1
            continue

        if not token.startswith("-"):
            break
        index += 1

    if not targets:
        return False, None

    nonempty = [target for target in targets if target]
    if len(nonempty) != 1 or len(targets) != 1:
        return True, None
    return True, nonempty[0]


def _directory_target_for_command(command: str) -> tuple[bool, str | None]:
    tokens = _package_command_tokens(command.strip())
    if not tokens:
        return False, None

    manager = tokens[0].lower()
    if manager not in {"npm", "pnpm", "yarn", "bun"}:
        return False, None

    supported_options: set[str]
    supported_long_options: set[str]
    if manager == "pnpm":
        supported_options = {"--dir", "-C"}
        supported_long_options = {"--dir"}
    elif manager == "npm":
        supported_options = {"--prefix"}
        supported_long_options = {"--prefix"}
    elif manager in {"yarn", "bun"}:
        supported_options = {"--cwd"}
        supported_long_options = {"--cwd"}
    else:
        return False, None

    targets: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in supported_options:
            if index + 1 < len(tokens):
                targets.append(tokens[index + 1])
            else:
                targets.append("")
            index += 2
            continue

        matched_inline = False
        for option in supported_long_options:
            prefix = f"{option}="
            if token.startswith(prefix):
                targets.append(token[len(prefix):])
                matched_inline = True
                break
        if matched_inline:
            index += 1
            continue

        if token in {"--filter", "-F", "--workspace", "-w"}:
            index += 2
            continue
        if token.startswith(("--filter=", "--workspace=")):
            index += 1
            continue

        if manager == "yarn" and token == "workspace":
            break
        if not token.startswith("-"):
            break
        index += 1

    if not targets:
        return False, None
    nonempty = [target for target in targets if target]
    if len(nonempty) != 1 or len(targets) != 1:
        return True, None
    return True, nonempty[0]


def _safe_repository_directory(root: Path, target: str) -> Path | None:
    value = target.strip().replace("\\", "/")
    if not value or value.startswith("/") or re.match(r"^[A-Za-z]:/", value):
        return None

    parts = [part for part in value.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        return None

    candidate = root.joinpath(*parts) if parts else root
    try:
        candidate.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return candidate


def _directory_script_names(root: Path, target: str) -> set[str] | None:
    directory = _safe_repository_directory(root, target)
    if directory is None:
        return None

    package_path = directory / "package.json"
    if not package_path.is_file() or package_path.is_symlink():
        return None

    package = _package_json(package_path)
    raw_scripts = package.get("scripts")
    if not isinstance(raw_scripts, dict):
        return set()
    return {
        str(name)
        for name, value in raw_scripts.items()
        if isinstance(name, str) and isinstance(value, str)
    }


def _workspace_script_names(root: Path, target: str) -> set[str] | None:
    matches: list[set[str]] = []
    for directory, _dirnames, filenames in _walk_repository(root):
        if "package.json" not in filenames:
            continue
        package_path = directory / "package.json"
        package = _package_json(package_path)
        if package.get("name") != target:
            continue
        raw_scripts = package.get("scripts")
        if isinstance(raw_scripts, dict):
            scripts = {
                str(name)
                for name, value in raw_scripts.items()
                if isinstance(name, str) and isinstance(value, str)
            }
        else:
            scripts = set()
        matches.append(scripts)

    if len(matches) != 1:
        return None
    return matches[0]


def _script_names_for_command(root: Path, scope: str, command: str) -> set[str] | None:
    has_workspace_target, workspace_target = _workspace_target_for_command(command)
    if has_workspace_target:
        if workspace_target is None:
            return None
        return _workspace_script_names(root, workspace_target)

    has_directory_target, directory_target = _directory_target_for_command(command)
    if has_directory_target:
        if directory_target is None:
            return None
        return _directory_script_names(root, directory_target)

    return _script_names(root, scope)


def _manager_for_command(command: str) -> str | None:
    match = _PACKAGE_COMMAND.match(command.strip())
    return match.group(1).lower() if match else None


_PACKAGE_OPTIONS_WITH_VALUE = {
    "--filter",
    "-F",
    "--workspace",
    "-w",
    "--prefix",
    "--dir",
    "-C",
    "--cwd",
}


def _package_command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def _script_for_command(command: str) -> tuple[str, str, bool] | None:
    tokens = _package_command_tokens(command.strip())
    if not tokens:
        return None

    manager = tokens[0].lower()
    if manager not in {"npm", "pnpm", "yarn", "bun"}:
        return None

    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in _PACKAGE_OPTIONS_WITH_VALUE:
            index += 2
            continue
        if any(token.startswith(f"{option}=") for option in _PACKAGE_OPTIONS_WITH_VALUE if option.startswith("--")):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        break

    if index >= len(tokens):
        return None

    if manager == "yarn" and tokens[index] == "workspace":
        index += 2
        if index >= len(tokens):
            return None

    explicit_run = tokens[index] in {"run", "run-script"}
    if explicit_run:
        index += 1
        while index < len(tokens) and tokens[index].startswith("-"):
            if tokens[index] in _PACKAGE_OPTIONS_WITH_VALUE:
                index += 2
            else:
                index += 1
        if index >= len(tokens):
            return None

    script = tokens[index]
    if script in {"install", "ci", "exec", "dlx", "workspace"}:
        return None

    return manager, script, explicit_run


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
    manager, script, _explicit_run = parsed
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

        for command in commands:
            parsed = _script_for_command(command)
            if not parsed:
                continue
            scripts = _script_names_for_command(root, signal.scope, command)
            if scripts is None:
                continue
            _manager, script, explicit_run = parsed
            if script not in scripts and (script == "test" or explicit_run):
                findings.append(
                    InstructionFinding(
                        "missing-package-script",
                        "warning",
                        f"{path} references '{command}', but the targeted or nearest package.json for scope '{signal.scope}' has no '{script}' script.",
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
