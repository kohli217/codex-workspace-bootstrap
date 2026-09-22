# Scoped monorepo demo: nearest package-manager evidence

This is a **reproducible product demo**, not a claim of third-party adoption.

It creates two temporary Git repositories that mimic a common JavaScript monorepo layout:

- the repository root uses **npm**;
- `apps/web` uses **pnpm**;
- the root `AGENTS.md` correctly uses npm;
- the nested `apps/web/AGENTS.md` initially uses the wrong package manager.

CWB should evaluate each instruction file against the nearest repository evidence instead of treating the whole monorepo as one package-manager scope.

## Expected result

```text
=== BEFORE ===
State: NEEDS ATTENTION
...
package-manager-mismatch
Scope: apps/web

=== AFTER ===
State: READY
Findings: none

Demo verification: PASS
```

## Run it

From a clone of this repository:

```powershell
py -m pip install -e .
py examples/scoped-monorepo-demo/run_demo.py
```

On macOS/Linux:

```bash
python -m pip install -e .
python examples/scoped-monorepo-demo/run_demo.py
```

The script exits non-zero if the scoped detection behavior changes, so CI runs it as a regression check.

## Why this matters

A monorepo may legitimately use different package managers or validation commands in different subtrees. A root-level npm rule should not force a nested pnpm application to use npm, and a nested mistake should not be misreported as repository-wide drift.

The demo verifies both sides:

1. CWB catches the incorrect nested `npm test` because the closest `apps/web/package.json` and `pnpm-lock.yaml` say pnpm.
2. After changing only the nested instruction to `pnpm test`, CWB reports the repository as READY.
