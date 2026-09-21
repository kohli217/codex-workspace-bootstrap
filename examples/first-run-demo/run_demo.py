from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from codex_workspace_bootstrap.preflight import build_preflight


def _write_demo_repository(root: Path, *, fixed: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)

    (root / "README.md").write_text(
        "# Demo app\n\nA tiny repository used to demonstrate AI-instruction preflight checks.\n",
        encoding="utf-8",
    )
    (root / ".gitignore").write_text(
        "node_modules/\n.env\n",
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": "cwb-preflight-demo",
                "private": True,
                "packageManager": "pnpm@10.0.0",
                "scripts": {
                    "test": "node -e \"console.log('tests passed')\""
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "pnpm-lock.yaml").write_text(
        "lockfileVersion: '9.0'\n",
        encoding="utf-8",
    )

    if fixed:
        instructions = """# AGENTS.md

This repository uses pnpm.

Validate changes with:

```bash
pnpm test
```
"""
    else:
        instructions = """# AGENTS.md

This repository uses npm.

Validate changes with:

```bash
npm test
npm run lint
```
"""

    (root / "AGENTS.md").write_text(instructions, encoding="utf-8")

    git = shutil.which("git")
    if git:
        subprocess.run(
            [git, "init", "-q", str(root)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _show(label: str, report: dict[str, object]) -> None:
    integrity = report["instruction_summary"]
    print(f"\n=== {label} ===")
    print(f"State: {report['state']}")
    print(
        "Instruction integrity: "
        f"{integrity['findings']} findings, "
        f"{integrity['drift']} drift, "
        f"{integrity['invalid_commands']} invalid commands, "
        f"{integrity['metadata']} metadata"
    )

    findings = report["instruction_findings"]
    if findings:
        print("Findings:")
        for item in findings:
            print(f"  - {item['kind']}: {item['message']}")
    else:
        print("Findings: none")


def main() -> int:
    if shutil.which("git") is None:
        print("error: git is required for the reproducible demo")
        return 2

    with tempfile.TemporaryDirectory(prefix="cwb-demo-") as temp:
        base = Path(temp)
        before = base / "before"
        after = base / "after"

        _write_demo_repository(before, fixed=False)
        _write_demo_repository(after, fixed=True)

        before_report = build_preflight(before)
        after_report = build_preflight(after)

        _show("BEFORE", before_report)
        _show("AFTER", after_report)

        before_kinds = {
            item["kind"] for item in before_report["instruction_findings"]
        }

        expected_before = {
            "package-manager-mismatch",
            "missing-package-script",
        }
        if before_report["state"] != "NEEDS ATTENTION":
            print(
                "error: expected BEFORE state NEEDS ATTENTION, "
                f"got {before_report['state']}"
            )
            return 1
        if not expected_before.issubset(before_kinds):
            missing = sorted(expected_before - before_kinds)
            print(f"error: BEFORE demo did not detect expected findings: {missing}")
            return 1
        if after_report["state"] != "READY":
            print(
                "error: expected AFTER state READY, "
                f"got {after_report['state']}"
            )
            return 1
        if after_report["instruction_findings"]:
            print("error: AFTER demo still has instruction-integrity findings")
            return 1

        print("\nDemo verification: PASS")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
