# Multi-agent Python demo

This reproducible demo shows how CWB distinguishes **same-scope cross-agent drift** from a **path-specific rule**.

It creates temporary repositories only; it does not modify the current repository and it does not execute any command extracted from AI instruction files.

## Run

From the repository root:

```powershell
python examples/multi-agent-python-demo/run_demo.py
```

## Before

The root instruction files disagree on the Python type-check command:

- `AGENTS.md` -> `mypy src`
- `CLAUDE.md` -> `pyright src`

A Copilot rule scoped to `tests/**/*.py` separately uses `ruff check tests`.

Expected result:

```text
=== BEFORE ===
State: NEEDS ATTENTION
validation-command-drift
```

The path-specific Copilot rule is intentionally not compared as if it were another repository-wide root instruction.

## After

Claude is changed to the wrapper-equivalent command `python -m mypy src`.

CWB normalizes both root instructions to the same typecheck baseline, so the drift disappears:

```text
=== AFTER ===
State: READY
Findings: none

Demo verification: PASS
```

This is a deterministic technical example, not a claim of third-party adoption.
