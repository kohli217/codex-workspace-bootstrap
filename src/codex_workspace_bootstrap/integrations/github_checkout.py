from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

from .github_webhook import GitHubWebhookTarget


_REPOSITORY_PART = re.compile(r"^[A-Za-z0-9_.-]+$")
_COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{40,64}$")


class GitHubCheckoutError(RuntimeError):
    """Raised when a GitHub webhook target cannot be checked out safely."""


@dataclass(frozen=True)
class GitHubCheckoutCandidate:
    ref: str
    expected_sha: str


@dataclass(frozen=True)
class GitHubCheckoutPlan:
    repository: str
    candidates: tuple[GitHubCheckoutCandidate, ...]


@dataclass(frozen=True)
class GitHubCheckoutResult:
    root: Path
    commit_sha: str
    fetched_ref: str


def _validate_repository(repository: str) -> tuple[str, str]:
    parts = repository.split("/")
    if (
        len(parts) != 2
        or not all(parts)
        or not all(_REPOSITORY_PART.fullmatch(part) for part in parts)
    ):
        raise GitHubCheckoutError("repository must use a valid GitHub owner/name form")
    return parts[0], parts[1]


def _validate_sha(value: str, field: str) -> str:
    if not _COMMIT_SHA.fullmatch(value):
        raise GitHubCheckoutError(f"{field} must be a hexadecimal commit SHA")
    return value.lower()


def build_github_checkout_plan(target: GitHubWebhookTarget) -> GitHubCheckoutPlan:
    """Build deterministic Git fetch candidates for a webhook event."""

    _validate_repository(target.repository)
    head_sha = _validate_sha(target.head_sha, "head_sha")
    candidates: list[GitHubCheckoutCandidate] = []

    if target.event == "pull_request":
        if target.pull_request_number is None or target.pull_request_number <= 0:
            raise GitHubCheckoutError("pull request target is missing its number")

        if target.merge_commit_sha:
            merge_sha = _validate_sha(
                target.merge_commit_sha,
                "merge_commit_sha",
            )
            candidates.extend(
                [
                    GitHubCheckoutCandidate(merge_sha, merge_sha),
                    GitHubCheckoutCandidate(
                        f"refs/pull/{target.pull_request_number}/merge",
                        merge_sha,
                    ),
                ]
            )

        candidates.extend(
            [
                GitHubCheckoutCandidate(head_sha, head_sha),
                GitHubCheckoutCandidate(
                    f"refs/pull/{target.pull_request_number}/head",
                    head_sha,
                ),
            ]
        )

    elif target.event == "push":
        candidates.append(GitHubCheckoutCandidate(head_sha, head_sha))
        if target.ref:
            candidates.append(GitHubCheckoutCandidate(target.ref, head_sha))
    else:
        raise GitHubCheckoutError(
            f"unsupported checkout event: {target.event}"
        )

    return GitHubCheckoutPlan(
        repository=target.repository,
        candidates=tuple(candidates),
    )


def _run_git(
    args: Sequence[str],
    *,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _git_environment(
    *,
    installation_token: str,
    hooks_path: str,
) -> dict[str, str]:
    if not installation_token.strip():
        raise GitHubCheckoutError("installation token must not be empty")

    env = os.environ.copy()
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Bearer {installation_token}",
            "GIT_CONFIG_KEY_1": "core.hooksPath",
            "GIT_CONFIG_VALUE_1": hooks_path,
        }
    )
    return env


def checkout_github_repository(
    plan: GitHubCheckoutPlan,
    *,
    installation_token: str,
    destination: Path,
) -> GitHubCheckoutResult:
    """Fetch one exact webhook revision without executing repository code."""

    owner, repo = _validate_repository(plan.repository)
    if not plan.candidates:
        raise GitHubCheckoutError("checkout plan has no candidates")
    if destination.exists():
        raise GitHubCheckoutError("checkout destination must not already exist")
    if shutil.which("git") is None:
        raise GitHubCheckoutError("git command is required for repository checkout")

    remote_url = f"https://github.com/{owner}/{repo}.git"
    destination = destination.resolve()
    created = False

    try:
        with tempfile.TemporaryDirectory(prefix="cwb-git-hooks-") as hooks_dir:
            env = _git_environment(
                installation_token=installation_token,
                hooks_path=hooks_dir,
            )

            init = _run_git(
                ("git", "init", "--quiet", str(destination)),
                env=env,
            )
            if init.returncode != 0:
                raise GitHubCheckoutError("could not initialize checkout directory")
            created = True

            remote = _run_git(
                (
                    "git",
                    "-C",
                    str(destination),
                    "remote",
                    "add",
                    "origin",
                    remote_url,
                ),
                env=env,
            )
            if remote.returncode != 0:
                raise GitHubCheckoutError("could not configure GitHub checkout remote")

            selected: GitHubCheckoutCandidate | None = None
            selected_sha: str | None = None

            for candidate in plan.candidates:
                fetch = _run_git(
                    (
                        "git",
                        "-C",
                        str(destination),
                        "fetch",
                        "--no-tags",
                        "--depth=1",
                        "origin",
                        candidate.ref,
                    ),
                    env=env,
                )
                if fetch.returncode != 0:
                    continue

                resolved = _run_git(
                    (
                        "git",
                        "-C",
                        str(destination),
                        "rev-parse",
                        "FETCH_HEAD",
                    ),
                    env=env,
                )
                actual_sha = resolved.stdout.strip().lower()
                if (
                    resolved.returncode != 0
                    or not _COMMIT_SHA.fullmatch(actual_sha)
                    or actual_sha != candidate.expected_sha
                ):
                    continue

                selected = candidate
                selected_sha = actual_sha
                break

            if selected is None or selected_sha is None:
                raise GitHubCheckoutError(
                    "could not fetch the exact webhook revision from GitHub"
                )

            checkout = _run_git(
                (
                    "git",
                    "-C",
                    str(destination),
                    "checkout",
                    "--detach",
                    "--quiet",
                    "FETCH_HEAD",
                ),
                env=env,
            )
            if checkout.returncode != 0:
                raise GitHubCheckoutError("could not check out fetched revision")

            return GitHubCheckoutResult(
                root=destination,
                commit_sha=selected_sha,
                fetched_ref=selected.ref,
            )
    except Exception:
        if created and destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        raise
