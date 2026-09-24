# AGENTS.md

## Mission

Maintain `codex-workspace-bootstrap` as a small, safe, dependency-light tool that helps Windows developers prepare repositories for effective Codex-assisted maintenance.

## Before editing

1. Read `README.md`.
2. Read the relevant implementation and tests.
3. Keep changes focused on the issue or request.
4. Do not add telemetry, credentials, or network calls to the core audit path without explicit discussion.

## Engineering rules

- Keep Python compatibility at 3.10+.
- Prefer the Python standard library for core features.
- Preserve Windows behavior and PowerShell-first documentation.
- Commands that modify user projects must be opt-in and must not overwrite existing files without an explicit flag.
- Audit checks should report observable facts and avoid claiming that a repository is secure.
- Never print the contents of suspected secret files.
- Add or update tests for behavior changes.

## Validation

Run:

```powershell
python -m pytest -q
python -m codex_workspace_bootstrap audit .
```

Install the platform-appropriate hash-locked test requirements from `.github/requirements-test-*.txt` first. The suite uses pytest functions and fixtures; `unittest discover` does not run these tests.

This is also supported:

```powershell
pytest
```

Before completion, inspect the diff for accidental generated files or credentials.
