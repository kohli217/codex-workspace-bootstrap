from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .agents import generate_agents
from .audit import audit_repository, summary
from .doctor import doctor_findings
from .sarif import checks_to_sarif


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-workspace-bootstrap",
        description="Audit and bootstrap repositories for reliable Codex workflows.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

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
    if args.command == "audit":
        return _run_audit(args.path, args.json_path, args.sarif_path, args.strict)
    if args.command == "doctor":
        return _run_doctor(args.path)
    if args.command == "init-agents":
        return _run_init_agents(args.path, args.force)
    return 2
