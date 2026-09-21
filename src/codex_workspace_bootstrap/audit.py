from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import os
import shutil
import subprocess
from typing import Iterable

from .agents import detect_node_package_managers


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    message: str
    blocking: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


COMMON_TOOLS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("git", ("git", "--version")),
    ("python", ("python", "--version")),
    ("node", ("node", "--version")),
    ("powershell", ("powershell", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()")),
    ("wsl", ("wsl", "--status")),
    ("codex", ("codex", "--version")),
)

MANIFESTS = (
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
)

RISK_FILENAMES = {
    ".env",
    ".env.local",
    "credentials.json",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
}

RISK_SUFFIXES = (".pem", ".p12", ".pfx", ".key")

NODE_PACKAGE_MANAGER_COMMANDS: dict[str, tuple[str, ...]] = {
    "npm": ("npm", "--version"),
    "pnpm": ("pnpm", "--version"),
    "yarn": ("yarn", "--version"),
    "bun": ("bun", "--version"),
}


def _tool_check(label: str, command: tuple[str, ...]) -> Check:
    executable = shutil.which(command[0])
    if not executable:
        return Check(label, "warn", f"{command[0]} command not found")

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        output = (result.stdout or result.stderr).strip().splitlines()
        detail = output[0] if output else "available"
        if result.returncode == 0:
            return Check(label, "pass", detail)
        return Check(label, "warn", f"available but returned exit code {result.returncode}")
    except (OSError, subprocess.SubprocessError) as exc:
        return Check(label, "warn", f"could not execute: {exc}")


def _iter_project_files(root: Path) -> Iterable[Path]:
    excluded = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        "dist",
        "build",
    }

    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirnames[:] = [
            name
            for name in dirnames
            if name not in excluded and not (current_path / name).is_symlink()
        ]
        for filename in filenames:
            yield current_path / filename


def _git_tracked_files(root: Path) -> set[str] | None:
    if shutil.which("git") is None:
        return None
    try:
        result = subprocess.run(
            ("git", "-C", str(root), "ls-files", "-z"),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return None
        return {item for item in result.stdout.split("\0") if item}
    except (OSError, subprocess.SubprocessError):
        return None


def _git_matches(root: Path, args: tuple[str, ...]) -> bool:
    if shutil.which("git") is None:
        return False
    try:
        result = subprocess.run(
            ("git", "-C", str(root), *args),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _classify_risky_paths(
    root: Path,
    risky: list[str],
    tracked_files: set[str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    tracked: list[str] = []
    ignored: list[str] = []
    untracked: list[str] = []

    for relative in risky:
        if tracked_files is not None and relative in tracked_files:
            tracked.append(relative)
        elif tracked_files is None and _git_matches(root, ("ls-files", "--error-unmatch", "--", relative)):
            tracked.append(relative)
        elif _git_matches(root, ("check-ignore", "--quiet", "--", relative)):
            ignored.append(relative)
        else:
            untracked.append(relative)

    return tracked, ignored, untracked


def _is_risky_filename(name: str) -> bool:
    lowered = name.lower()
    return lowered in RISK_FILENAMES or lowered.endswith(RISK_SUFFIXES)


def _preview(paths: list[str], limit: int = 8) -> str:
    visible = ", ".join(sorted(paths)[:limit])
    suffix = "" if len(paths) <= limit else f" (+{len(paths) - limit} more)"
    return f"{visible}{suffix}"


def audit_repository(root: Path) -> list[Check]:
    root = root.resolve()
    checks: list[Check] = []

    git_dir = root / ".git"
    checks.append(
        Check(
            "git-repository",
            "pass" if git_dir.exists() else "warn",
            "Git repository detected" if git_dir.exists() else ".git directory not found",
        )
    )

    readme = next(
        (
            p
            for p in root.iterdir()
            if p.is_file() and not p.is_symlink() and p.name.lower().startswith("readme")
        ),
        None,
    )
    checks.append(
        Check(
            "readme",
            "pass" if readme else "warn",
            f"README detected: {readme.name}" if readme else "README not found",
        )
    )

    license_file = next(
        (
            p
            for p in root.iterdir()
            if p.is_file() and not p.is_symlink() and p.name.lower().startswith("license")
        ),
        None,
    )
    checks.append(
        Check(
            "license",
            "pass" if license_file else "warn",
            f"License detected: {license_file.name}" if license_file else "License file not found",
        )
    )

    checks.append(
        Check(
            "gitignore",
            "pass"
            if (root / ".gitignore").is_file() and not (root / ".gitignore").is_symlink()
            else "warn",
            ".gitignore detected"
            if (root / ".gitignore").is_file() and not (root / ".gitignore").is_symlink()
            else ".gitignore not found",
        )
    )

    checks.append(
        Check(
            "agents",
            "pass"
            if (root / "AGENTS.md").is_file() and not (root / "AGENTS.md").is_symlink()
            else "warn",
            "AGENTS.md detected"
            if (root / "AGENTS.md").is_file() and not (root / "AGENTS.md").is_symlink()
            else "AGENTS.md not found; run init-agents",
        )
    )

    manifests = [
        name
        for name in MANIFESTS
        if (root / name).is_file() and not (root / name).is_symlink()
    ]
    checks.append(
        Check(
            "project-manifest",
            "pass" if manifests else "warn",
            f"Detected: {', '.join(manifests)}" if manifests else "No common project manifest detected",
        )
    )

    for label, command in COMMON_TOOLS:
        checks.append(_tool_check(label, command))

    if (root / "package.json").is_file() and not (root / "package.json").is_symlink():
        managers = detect_node_package_managers(root)
        if managers:
            if len(managers) > 1:
                checks.append(
                    Check(
                        "package-manager-evidence",
                        "warn",
                        "Conflicting Node.js package-manager evidence detected: "
                        + ", ".join(sorted(managers)),
                    )
                )
            for manager in sorted(managers):
                command = NODE_PACKAGE_MANAGER_COMMANDS[manager]
                checks.append(_tool_check(manager, command))
        else:
            checks.append(
                Check(
                    "package-manager-evidence",
                    "warn",
                    "Node.js project detected, but packageManager/lockfile evidence does not confirm npm, pnpm, yarn, or bun",
                )
            )

    tracked_files = _git_tracked_files(root)
    risky: set[str] = set()

    for path in _iter_project_files(root):
        if _is_risky_filename(path.name):
            risky.add(path.relative_to(root).as_posix())

    # Generated/dependency directories are pruned from the filesystem walk to
    # avoid expensive scans. Tracked files are different: if a risky filename
    # is committed, it must still be surfaced even inside a pruned directory.
    if tracked_files is not None:
        risky.update(
            relative
            for relative in tracked_files
            if _is_risky_filename(Path(relative).name)
        )

    if risky:
        tracked, ignored, untracked = _classify_risky_paths(
            root,
            sorted(risky),
            tracked_files,
        )
        parts: list[str] = []
        if tracked:
            parts.append(f"tracked: {_preview(tracked)}")
        if ignored:
            parts.append(f"ignored: {_preview(ignored)}")
        if untracked:
            parts.append(f"untracked/unknown: {_preview(untracked)}")

        checks.append(
            Check(
                "secret-risk-files",
                "warn",
                "Potential secret-bearing filenames detected (" + "; ".join(parts) + "). "
                "The audit does not read file contents.",
                blocking=bool(tracked),
            )
        )
    else:
        checks.append(Check("secret-risk-files", "pass", "No common secret-bearing filenames detected"))

    return checks


def summary(checks: list[Check]) -> dict[str, int]:
    return {
        "passed": sum(c.status == "pass" for c in checks),
        "warnings": sum(c.status == "warn" for c in checks),
        "blocking": sum(c.blocking for c in checks),
    }
