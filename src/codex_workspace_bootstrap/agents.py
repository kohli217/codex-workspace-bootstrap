from __future__ import annotations

import json
from pathlib import Path


PYTHON_MARKERS = ("pyproject.toml", "requirements.txt", "setup.py", "setup.cfg")
NODE_MARKER = "package.json"


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


def validation_commands(root: Path) -> list[str]:
    signals = detect_project_signals(root)
    commands: list[str] = []

    if "Python" in signals:
        if (root / "tests").is_dir():
            commands.append("python -m pytest")
        else:
            commands.append("python -m compileall .")

    if "Node.js" in signals:
        scripts = _node_script_names(root)
        if "test" in scripts:
            commands.append("npm test")
        if "lint" in scripts:
            commands.append("npm run lint")
        if not {"test", "lint"} & scripts:
            commands.append("npm install --ignore-scripts --package-lock-only --dry-run")

    commands.extend(
        [
            "codex-workspace-bootstrap audit . --strict",
            "git diff --check",
            "git status --short",
        ]
    )
    return commands


def generate_agents(root: Path) -> str:
    signals = detect_project_signals(root)
    signal_text = ", ".join(signals) if signals else "No common Python or Node.js manifest detected"
    commands = validation_commands(root)
    command_lines = "\n".join(f"- `{command}`" for command in commands)

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

## Suggested validation

Run the commands that apply to the change:

{command_lines}

If a generated command does not match the repository's documented workflow, follow the repository documentation and update this file rather than forcing the command to run.

## Safety

- Do not print the contents of files suspected to contain secrets.
- Do not overwrite user files without explicit approval.
- Treat successful automated checks as evidence, not as a security guarantee.
"""
