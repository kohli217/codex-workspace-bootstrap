from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from codex_workspace_bootstrap.preflight import build_preflight


def _write_repository(root: Path, *, fixed: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)

    (root / "README.md").write_text(
        "# Scoped monorepo demo\n\nA temporary repository for CWB scope checks.\n",
        encoding="utf-8",
    )
    (root / ".gitignore").write_text(
        "node_modules/\n.env\n",
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": "cwb-scoped-monorepo-demo",
                "private": True,
                "packageManager": "npm@11.0.0",
                "scripts": {
                    "test": "node -e \"console.log('root tests passed')\""
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "package-lock.json").write_text("{}\n", encoding="utf-8")
    (root / "AGENTS.md").write_text(
        """# Root instructions

The repository root uses npm.

Validate root changes with:

```bash
npm test
```
""",
        encoding="utf-8",
    )

    web = root / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text(
        json.dumps(
            {
                "name": "web",
                "private": True,
                "packageManager": "pnpm@10.0.0",
                "scripts": {
                    "test": "node -e \"console.log('web tests passed')\""
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (web / "pnpm-lock.yaml").write_text(
        "lockfileVersion: '9.0'\n",
        encoding="utf-8",
    )
    nested_command = "pnpm test" if fixed else "npm test"
    (web / "AGENTS.md").write_text(
        f"""# Web instructions

The web application has its own package-manager evidence.

Validate web changes with:

```bash
{nested_command}
```
""",
        encoding="utf-8",
    )

    git = shutil.which("git")
    if git:
        subprocess.run(
            [git, "init", "-q", str(root)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _show(label: str, report: dict[str, object]) -> None:
    print(f"\n=== {label} ===")
    print(f"State: {report['state']}")

    findings = report["instruction_findings"]
    if findings:
        print("Findings:")
        for item in findings:
            print(
                f"  - {item['kind']} "
                f"(scope: {item.get('scope', '.')}): {item['message']}"
            )
    else:
        print("Findings: none")


def main() -> int:
    if shutil.which("git") is None:
        print("error: git is required for the reproducible demo")
        return 2

    with tempfile.TemporaryDirectory(prefix="cwb-scoped-demo-") as temp:
        base = Path(temp)
        before = base / "before"
        after = base / "after"

        _write_repository(before, fixed=False)
        _write_repository(after, fixed=True)

        before_report = build_preflight(before)
        after_report = build_preflight(after)

        _show("BEFORE", before_report)
        _show("AFTER", after_report)

        before_mismatches = [
            item
            for item in before_report["instruction_findings"]
            if item["kind"] == "package-manager-mismatch"
        ]

        if before_report["state"] != "NEEDS ATTENTION":
            print(
                "error: expected BEFORE state NEEDS ATTENTION, "
                f"got {before_report['state']}"
            )
            return 1

        if len(before_mismatches) != 1:
            print(
                "error: expected exactly one nested package-manager mismatch, "
                f"got {len(before_mismatches)}"
            )
            return 1

        mismatch = before_mismatches[0]
        if mismatch.get("scope") != "apps/web":
            print(
                "error: expected mismatch scope apps/web, "
                f"got {mismatch.get('scope')}"
            )
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
