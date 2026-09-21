# First-run demo: see the problem, then the fix

This is a **reproducible product demo**, not a claim of third-party adoption.

It creates two temporary Git repositories and runs the real `codex-workspace-bootstrap` preflight against both.

## What the demo proves

The **BEFORE** repository deliberately contains two common AI-coding setup mistakes:

- the repository declares **pnpm**, while `AGENTS.md` tells the agent to use **npm**;
- `AGENTS.md` tells the agent to run `npm run lint`, but no `lint` script exists.

The **AFTER** repository uses the same project metadata with corrected instructions.

Expected result:

```text
=== BEFORE ===
State: NEEDS ATTENTION
...
package-manager-mismatch
missing-package-script

=== AFTER ===
State: READY
Findings: none

Demo verification: PASS
```

## Run it

From a clone of this repository:

```powershell
py -m pip install -e .
py examples/first-run-demo/run_demo.py
```

On macOS/Linux:

```bash
python -m pip install -e .
python examples/first-run-demo/run_demo.py
```

The script exits non-zero if the expected detection behavior changes, so CI runs it as a regression check.

## Why a temporary repository?

The main project self-checks its own AI instructions. Keeping deliberately broken `AGENTS.md` files inside the repository tree would pollute the real preflight.

Instead, this demo materializes disposable repositories at runtime, exercises the actual detector, and removes them automatically afterward.

## Try the same check on your repository

```powershell
py -m pip install codex-workspace-bootstrap
cwb preflight .
```

Project:

https://github.com/kohli217/codex-workspace-bootstrap
