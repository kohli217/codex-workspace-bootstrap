from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile

from codex_workspace_bootstrap.preflight import build_preflight


def _write_repository(root: Path, *, fixed: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)

    (root / "README.md").write_text(
        "# Multi-agent Python demo\n\n"
        "A temporary repository for cross-agent validation checks.\n",
        encoding="utf-8",
    )
    (root / ".gitignore").write_text(
        ".venv/\n__pycache__/\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "cwb-multi-agent-python-demo"\n'
        'version = "0.0.0"\n',
        encoding="utf-8",
    )

    (root / "src").mkdir()
    (root / "src" / "demo.py").write_text(
        "def answer() -> int:\n"
        "    return 42\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_demo.py").write_text(
        "from src.demo import answer\n\n"
        "def test_answer() -> None:\n"
        "    assert answer() == 42\n",
        encoding="utf-8",
    )

    (root / "AGENTS.md").write_text(
        """# Codex instructions

Type-check Python changes with:

```bash
mypy src
```
""",
        encoding="utf-8",
    )

    claude_command = "python -m mypy src" if fixed else "pyright src"
    (root / "CLAUDE.md").write_text(
        f"""# Claude Code instructions

Type-check Python changes with:

```bash
{claude_command}
```
""",
        encoding="utf-8",
    )

    copilot_dir = root / ".github" / "instructions"
    copilot_dir.mkdir(parents=True)
    (copilot_dir / "tests.instructions.md").write_text(
        """---
applyTo: "tests/**/*.py"
---

For test-only changes, lint the tests with:

```bash
ruff check tests
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

    print("AI instruction coverage:")
    for item in report["instruction_signals"]:
        print(
            f"  - {item['tool']}: {item['path']} "
            f"[scope={item.get('scope', '.')}, kind={item.get('kind', 'repository')}]"
        )

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

    with tempfile.TemporaryDirectory(prefix="cwb-multi-agent-python-") as temp:
        base = Path(temp)
        before = base / "before"
        after = base / "after"

        _write_repository(before, fixed=False)
        _write_repository(after, fixed=True)

        before_report = build_preflight(
            before,
            include_local_toolchain=False,
        )
        after_report = build_preflight(
            after,
            include_local_toolchain=False,
        )

        _show("BEFORE", before_report)
        _show("AFTER", after_report)

        before_drift = [
            item
            for item in before_report["instruction_findings"]
            if item["kind"] == "validation-command-drift"
        ]

        if before_report["state"] != "NEEDS ATTENTION":
            print(
                "error: expected BEFORE state NEEDS ATTENTION, "
                f"got {before_report['state']}"
            )
            return 1

        if len(before_drift) != 1:
            print(
                "error: expected exactly one validation-command-drift finding, "
                f"got {len(before_drift)}"
            )
            return 1

        drift = before_drift[0]
        if drift.get("scope") != "." or "typecheck" not in drift.get("message", ""):
            print(
                "error: expected root-scope typecheck drift, "
                f"got scope={drift.get('scope')} message={drift.get('message')}"
            )
            return 1

        files = set(drift.get("files", []))
        if files != {"AGENTS.md", "CLAUDE.md"}:
            print(
                "error: path-specific Copilot rule should not join root drift; "
                f"got files={sorted(files)}"
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
