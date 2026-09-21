from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


PYTHON_MARKERS = ("pyproject.toml", "requirements.txt", "setup.py", "setup.cfg")
NODE_MARKER = "package.json"
README_NAMES = ("README.md", "README.rst", "README.txt", "README")


@dataclass(frozen=True)
class ValidationCommand:
    command: str
    evidence: str
    review_required: bool = False


def detect_project_signals(root: Path) -> list[str]:
    signals: list[str] = []
    if any((root / marker).exists() for marker in PYTHON_MARKERS):
        signals.append("Python")
    if (root / NODE_MARKER).exists():
        signals.append("Node.js")
    return signals


def _node_script_names(root: Path) -> set[str]:
    package_json = root / NODE_MARKER
    if not package_json.exists():
        return set()

    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return set()

    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return set()

    return {name for name, value in scripts.items() if isinstance(name, str) and isinstance(value, str)}


def _readme_text(root: Path) -> str:
    for name in README_NAMES:
        path = root / name
        if path.is_file():
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
        "npm test",
        "npm run lint",
        "npm run build",
    }
    found: set[str] = set()
    for command in candidates:
        pattern = rf"(?m)(^|[\s$>]){re.escape(command)}(?=$|\s)"
        if re.search(pattern, text):
            found.add(command)
    return found


def _pyproject_has_pytest(root: Path) -> bool:
    path = root / "pyproject.toml"
    if not path.is_file():
        return False

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    if re.search(r"(?mi)^\\[tool\\.pytest(?:\\.|\\])", text):
        return True

    dependency_pattern = r"""(?i)["']pytest(?:[<>=!~\\[].*?)?["']"""
    return re.search(dependency_pattern, text) is not None


def validation_plan(root: Path) -> list[ValidationCommand]:
    signals = detect_project_signals(root)
    documented = _documented_commands(root)
    plan: list[ValidationCommand] = []

    if "Python" in signals:
        pytest_evidence = (
            _pyproject_has_pytest(root)
            or (root / "pytest.ini").exists()
            or (root / "conftest.py").exists()
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
        if "test" in scripts:
            plan.append(ValidationCommand("npm test", "package.json defines scripts.test"))
        if "lint" in scripts:
            plan.append(ValidationCommand("npm run lint", "package.json defines scripts.lint"))
        if "build" in scripts and "npm run build" in documented:
            plan.append(ValidationCommand("npm run build", "package.json defines scripts.build and README documents it"))
        if not {"test", "lint"} & scripts:
            plan.append(
                ValidationCommand(
                    "npm install --ignore-scripts --package-lock-only --dry-run",
                    "Node.js project detected; no test or lint script confirmed",
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
    signal_text = ", ".join(signals) if signals else "No common Python or Node.js manifest detected"
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
