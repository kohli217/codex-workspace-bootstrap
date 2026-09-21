from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .agents import generate_agents
from .audit import audit_repository, summary
from .doctor import doctor_findings
from .fixes import apply_fix_plan, build_fix_plan
from .preflight import build_preflight, render_markdown
from .sarif import checks_to_sarif


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-workspace-bootstrap",
        description="Audit and bootstrap repositories for reliable Codex workflows.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    preflight = sub.add_parser("preflight", help="Run the one-command AI repository readiness check")
    preflight.add_argument("path", nargs="?", default=".")
    preflight.add_argument("--json", dest="json_path", help="Write the complete preflight report to JSON")
    preflight.add_argument("--markdown", dest="markdown_path", help="Write a concise Markdown preflight report")
    preflight.add_argument(
        "--strict",
        action="store_true",
        help="Return a non-zero exit code when blocking findings are present",
    )
    preflight.add_argument(
        "--fail-on-integrity",
        action="store_true",
        help="Return a non-zero exit code when AI instruction integrity findings are present",
    )

    fix = sub.add_parser("fix", help="Preview safe repository-readiness fixes")
    fix.add_argument("path", nargs="?", default=".")
    fix.add_argument(
        "--apply",
        action="store_true",
        help="Apply only low-risk supported fixes; conflicting instructions are never auto-rewritten",
    )

    audit = sub.add_parser("audit", help="Audit a repository and local toolchain")
    audit.add_argument("path", nargs="?", default=".")
    audit.add_argument("--json", dest="json_path", help="Write the complete report to a JSON file")
    audit.add_argument("--sarif", dest="sarif_path", help="Write warnings and blocking findings as SARIF 2.1.0")
    audit.add_argument(
        "--strict",
        action="store_true",
        help="Return a non-zero exit code if blocking checks are present",
    )

    doctor = sub.add_parser("doctor", help="Diagnose warnings and print non-destructive remediation guidance")
    doctor.add_argument("path", nargs="?", default=".")

    init_agents = sub.add_parser("init-agents", help="Create a project-aware starter AGENTS.md")
    init_agents.add_argument("path", nargs="?", default=".")
    init_agents.add_argument("--force", action="store_true", help="Overwrite an existing AGENTS.md")

    return parser


def _write_json(path: str, payload: object, label: str) -> None:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"{label} written to: {output}")



def _run_preflight(
    path: str,
    json_path: str | None,
    markdown_path: str | None,
    strict: bool,
    fail_on_integrity: bool,
) -> int:
    root = Path(path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"error: repository path does not exist or is not a directory: {root}", file=sys.stderr)
        return 2

    report = build_preflight(root)

    print("AI Repository Preflight")
    print(f"Repository: {root}")
    print(f"State: {report['state']}")

    project_signals = report["project_signals"]
    project_text = ", ".join(project_signals) if project_signals else "Unknown"
    print(f"Project: {project_text}")

    instructions = report["instruction_signals"]
    if instructions:
        print("AI instructions:")
        for item in instructions:
            print(f"  - {item['tool']}: {item['path']} [scope={item.get('scope', '.')}]")
    else:
        print("AI instructions: none detected")

    totals = report["summary"]
    print(
        f"Audit: {totals['passed']} passed, "
        f"{totals['warnings']} warnings, {totals['blocking']} blocking"
    )

    instruction_totals = report["instruction_summary"]
    print(
        f"Instruction integrity: {instruction_totals['findings']} findings, "
        f"{instruction_totals['drift']} drift, "
        f"{instruction_totals['invalid_commands']} invalid commands, "
        f"{instruction_totals['metadata']} metadata"
    )

    findings = report["instruction_findings"]
    if findings:
        print("Instruction findings:")
        for item in findings:
            print(
                f"  [{item['severity'].upper()}] {item['kind']}: {item['message']} "
                f"[scope={item.get('scope', '.')}]"
            )

    actions = report["next_actions"]
    if actions:
        print("Next actions:")
        for item in actions:
            suffix = f" -> {item['command']}" if item.get("command") else ""
            print(f"  [{item['priority']}] {item['title']}{suffix}")
    else:
        print("Next actions: none")

    if json_path:
        _write_json(json_path, report, "Preflight JSON report")

    if markdown_path:
        output = Path(markdown_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_markdown(report), encoding="utf-8")
        print(f"Preflight Markdown report written to: {output}")

    if strict and report["state"] == "BLOCKED":
        return 1
    if fail_on_integrity and report["instruction_summary"]["findings"]:
        return 1
    return 0


def _run_fix(path: str, apply: bool) -> int:
    root = Path(path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"error: repository path does not exist or is not a directory: {root}", file=sys.stderr)
        return 2

    plan = build_fix_plan(root)
    print(f"Repository: {root}")
    if not plan:
        print("Fix plan: no supported fixes or instruction-integrity findings.")
        return 0

    print("Fix plan:")
    for item in plan:
        mode = "AUTO" if item.apply_supported else "REVIEW"
        target = f" -> {item.target}" if item.target else ""
        print(f"  [{mode}] {item.description}{target}")

    if not apply:
        print("Preview only. Re-run with --apply to apply low-risk supported fixes.")
        return 0

    applied = apply_fix_plan(root, plan)
    if applied:
        print("Applied:")
        for path_item in applied:
            print(f"  - {path_item}")
    else:
        print("No automatic changes were applied.")
    manual = sum(not item.apply_supported for item in plan)
    if manual:
        print(f"{manual} finding(s) require human review and were left unchanged.")
    return 0

def _run_audit(
    path: str,
    json_path: str | None,
    sarif_path: str | None,
    strict: bool,
) -> int:
    root = Path(path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"error: repository path does not exist or is not a directory: {root}", file=sys.stderr)
        return 2

    checks = audit_repository(root)
    totals = summary(checks)

    print(f"Repository: {root}")
    for check in checks:
        tag = "PASS" if check.status == "pass" else "WARN"
        print(f"[{tag}] {check.name}: {check.message}")

    print(
        f"Summary: {totals['passed']} passed, "
        f"{totals['warnings']} warnings, {totals['blocking']} blocking"
    )

    if json_path:
        _write_json(
            json_path,
            {
                "repository": str(root),
                "checks": [c.to_dict() for c in checks],
                "summary": totals,
            },
            "JSON report",
        )

    if sarif_path:
        _write_json(sarif_path, checks_to_sarif(checks), "SARIF report")

    if strict and totals["blocking"]:
        return 1
    return 0



def _run_doctor(path: str) -> int:
    root = Path(path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"error: repository path does not exist or is not a directory: {root}", file=sys.stderr)
        return 2

    findings = doctor_findings(audit_repository(root))

    print(f"Repository: {root}")
    if not findings:
        print("Doctor: no warnings detected by the current checks.")
        return 0

    for finding in findings:
        severity = "BLOCKING" if finding.blocking else "WARN"
        print(f"[{severity}] {finding.name}: {finding.message}")
        print(f"  Guidance: {finding.guidance}")

    print("Doctor is diagnostic only; it did not install software or modify configuration.")
    return 0

def _run_init_agents(path: str, force: bool) -> int:
    root = Path(path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"error: path does not exist or is not a directory: {root}", file=sys.stderr)
        return 2

    target = root / "AGENTS.md"
    if target.exists() and not force:
        print(f"error: {target} already exists; use --force to overwrite", file=sys.stderr)
        return 1

    target.write_text(generate_agents(root), encoding="utf-8")
    print(f"Created {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "preflight":
        return _run_preflight(
            args.path,
            args.json_path,
            args.markdown_path,
            args.strict,
            args.fail_on_integrity,
        )
    if args.command == "fix":
        return _run_fix(args.path, args.apply)
    if args.command == "audit":
        return _run_audit(args.path, args.json_path, args.sarif_path, args.strict)
    if args.command == "doctor":
        return _run_doctor(args.path)
    if args.command == "init-agents":
        return _run_init_agents(args.path, args.force)
    return 2
