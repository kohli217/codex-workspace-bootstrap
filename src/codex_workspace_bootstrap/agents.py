from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


PYTHON_MARKERS = ("pyproject.toml", "requirements.txt", "setup.py", "setup.cfg")
NODE_MARKER = "package.json"
GO_MARKERS = ("go.mod",)
RUST_MARKERS = ("Cargo.toml",)
JVM_MARKERS = (
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
)
DOTNET_SUFFIXES = (".sln", ".csproj", ".fsproj", ".vbproj")
README_NAMES = ("README.md", "README.rst", "README.txt", "README")


@dataclass(frozen=True)
class ValidationCommand:
    command: str
    evidence: str
    review_required: bool = False


def _regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def detect_project_signals(root: Path) -> list[str]:
    signals: list[str] = []
    if any(_regular_file(root / marker) for marker in PYTHON_MARKERS):
        signals.append("Python")
    if _regular_file(root / NODE_MARKER):
        signals.append("Node.js")
    if any(_regular_file(root / marker) for marker in GO_MARKERS):
        signals.append("Go")
    if any(_regular_file(root / marker) for marker in RUST_MARKERS):
        signals.append("Rust")
    if any(_regular_file(root / marker) for marker in JVM_MARKERS):
        signals.append("JVM")
    if any(
        _regular_file(path) and path.suffix.lower() in DOTNET_SUFFIXES
        for path in root.iterdir()
    ):
        signals.append(".NET")
    return signals


def _node_script_names(root: Path) -> set[str]:
    package_json = root / NODE_MARKER
    if not package_json.is_file() or package_json.is_symlink():
        return set()

    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return set()

    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return set()

    return {name for name, value in scripts.items() if isinstance(name, str) and isinstance(value, str)}


def detect_node_package_managers(root: Path) -> set[str]:
    managers: set[str] = set()
    package_json = root / NODE_MARKER

    if package_json.is_file() and not package_json.is_symlink():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            data = {}
        if isinstance(data, dict):
            declared = data.get("packageManager")
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
        candidate = root / filename
        if candidate.is_file() and not candidate.is_symlink():
            managers.add(manager)

    return managers


def _package_script_command(manager: str, script: str) -> str:
    if manager == "npm" and script == "test":
        return "npm test"
    return f"{manager} run {script}"


def _readme_text(root: Path) -> str:
    for name in README_NAMES:
        path = root / name
        if path.is_file() and not path.is_symlink():
            try:
                return path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return ""
    return ""


def _documented_commands(root: Path) -> set[str]:
    text = _readme_text(root)
    if not text:
        return set()

    candidates = {
        "python -m pytest",
        "pytest",
        "python -m unittest",
    }
    for manager in ("npm", "pnpm", "yarn", "bun"):
        for script in ("test", "lint", "build"):
            candidates.add(_package_script_command(manager, script))
    found: set[str] = set()
    for command in candidates:
        pattern = rf"(?m)(^|[\s$>]){re.escape(command)}(?=$|\s)"
        if re.search(pattern, text):
            found.add(command)
    return found


def _pyproject_has_pytest(root: Path) -> bool:
    path = root / "pyproject.toml"
    if not path.is_file() or path.is_symlink():
        return False

    try:
        text = path.read_text(encoding="utf-8").lower()
    except (OSError, UnicodeDecodeError):
        return False

    if "[tool.pytest" in text:
        return True

    dependency_prefixes = (
        '"pytest"',
        "'pytest'",
        '"pytest<',
        "'pytest<",
        '"pytest>',
        "'pytest>",
        '"pytest=',
        "'pytest=",
        '"pytest!',
        "'pytest!",
        '"pytest~',
        "'pytest~",
        '"pytest[',
        "'pytest[",
    )
    return any(prefix in text for prefix in dependency_prefixes)


def validation_plan(root: Path) -> list[ValidationCommand]:
    signals = detect_project_signals(root)
    documented = _documented_commands(root)
    plan: list[ValidationCommand] = []

    if "Python" in signals:
        pytest_evidence = (
            _pyproject_has_pytest(root)
            or _regular_file(root / "pytest.ini")
            or _regular_file(root / "conftest.py")
        )
        if "python -m pytest" in documented or "pytest" in documented:
            plan.append(ValidationCommand("python -m pytest", "documented in README"))
        elif pytest_evidence:
            plan.append(ValidationCommand("python -m pytest", "pytest configuration or dependency detected"))
        else:
            plan.append(ValidationCommand("python -m compileall .", "Python project detected; no test runner confirmed"))
            if (root / "tests").is_dir():
                plan.append(
                    ValidationCommand(
                        "python -m pytest",
                        "tests/ exists, but pytest was not confirmed in project metadata or README",
                        review_required=True,
                    )
                )

    if "Node.js" in signals:
        scripts = _node_script_names(root)
        managers = detect_node_package_managers(root)
        manager = next(iter(managers)) if len(managers) == 1 else None

        if manager:
            if "test" in scripts:
                plan.append(
                    ValidationCommand(
                        _package_script_command(manager, "test"),
                        f"package.json defines scripts.test and repository evidence selects {manager}",
                    )
                )
            if "lint" in scripts:
                plan.append(
                    ValidationCommand(
                        _package_script_command(manager, "lint"),
                        f"package.json defines scripts.lint and repository evidence selects {manager}",
                    )
                )
            build_command = _package_script_command(manager, "build")
            if "build" in scripts and build_command in documented:
                plan.append(
                    ValidationCommand(
                        build_command,
                        f"package.json defines scripts.build, repository evidence selects {manager}, and README documents it",
                    )
                )
        elif len(managers) > 1:
            # Conflicting package-manager evidence is handled by preflight.
            # Do not manufacture a manager-specific validation command here.
            pass
        else:
            # package.json alone does not prove npm. Preserve the historical
            # npm suggestions only as review-required hints until the project
            # supplies a lockfile, packageManager field, or documented command.
            if "test" in scripts:
                plan.append(
                    ValidationCommand(
                        "npm test",
                        "package.json defines scripts.test, but the package manager is not confirmed",
                        review_required=True,
                    )
                )
            if "lint" in scripts:
                plan.append(
                    ValidationCommand(
                        "npm run lint",
                        "package.json defines scripts.lint, but the package manager is not confirmed",
                        review_required=True,
                    )
                )

    plan.extend(
        [
            ValidationCommand(
                "codex-workspace-bootstrap audit . --strict",
                "repository readiness self-check",
            ),
            ValidationCommand("git diff --check", "generic Git whitespace validation"),
            ValidationCommand("git status --short", "generic Git change review"),
        ]
    )
    return plan


def validation_commands(root: Path) -> list[str]:
    return [item.command for item in validation_plan(root) if not item.review_required]


def generate_agents(root: Path) -> str:
    signals = detect_project_signals(root)
    signal_text = ", ".join(signals) if signals else "No supported project manifest detected"
    plan = validation_plan(root)

    confirmed = [item for item in plan if not item.review_required]
    review = [item for item in plan if item.review_required]

    confirmed_lines = "\n".join(
        f"- {item.command} — {item.evidence}"
        for item in confirmed
    )
    review_section = ""
    if review:
        review_lines = "\n".join(
            f"- {item.command} — {item.evidence}"
            for item in review
        )
        review_section = f"""
## Review-required suggestions

These commands are plausible from repository layout but are not sufficiently confirmed to treat as authoritative:

{review_lines}

Confirm them against project documentation or configuration before use.
"""

    return f"""# AGENTS.md

## Purpose

This repository is maintained with assistance from Codex.

## Detected project signals

{signal_text}

These signals are derived only from files present in the repository. Review this file before relying on the generated commands.

## Working rules

- Read README files and relevant project manifests before editing.
- Keep changes scoped to the requested issue or task.
- Do not add secrets, credentials, tokens, private data, or generated environment files.
- Prefer deterministic, scriptable commands over manual steps.
- Preserve existing platform support unless the task explicitly changes it.
- Add or update tests for behavior changes when the repository has a test suite.
- Explain user-visible behavior changes in the pull request or commit summary.
- Inspect the final diff before proposing completion.

## Confirmed validation

These commands have direct repository evidence or are generic non-destructive checks:

{confirmed_lines}
{review_section}
## Safety

- Do not print the contents of files suspected to contain secrets.
- Do not overwrite user files without explicit approval.
- Treat successful automated checks as evidence, not as a security guarantee.
"""
