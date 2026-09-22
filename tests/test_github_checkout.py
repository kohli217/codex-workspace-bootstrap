from pathlib import Path
import subprocess

import pytest

from codex_workspace_bootstrap.integrations.github_checkout import (
    GitHubCheckoutError,
    build_github_checkout_plan,
    checkout_github_repository,
)
from codex_workspace_bootstrap.integrations.github_webhook import GitHubWebhookTarget


HEAD = "a" * 40
MERGE = "b" * 40


def test_pull_request_checkout_prefers_exact_test_merge_commit() -> None:
    target = GitHubWebhookTarget(
        event="pull_request",
        repository="octo/demo",
        head_sha=HEAD,
        installation_id=123,
        action="synchronize",
        pull_request_number=42,
        merge_commit_sha=MERGE,
    )

    plan = build_github_checkout_plan(target)

    assert [(item.ref, item.expected_sha) for item in plan.candidates] == [
        (MERGE, MERGE),
        ("refs/pull/42/merge", MERGE),
        (HEAD, HEAD),
        ("refs/pull/42/head", HEAD),
    ]


def test_pull_request_without_test_merge_commit_falls_back_to_exact_head() -> None:
    target = GitHubWebhookTarget(
        event="pull_request",
        repository="octo/demo",
        head_sha=HEAD,
        installation_id=123,
        action="opened",
        pull_request_number=42,
    )

    plan = build_github_checkout_plan(target)

    assert [(item.ref, item.expected_sha) for item in plan.candidates] == [
        (HEAD, HEAD),
        ("refs/pull/42/head", HEAD),
    ]


def test_push_checkout_uses_exact_commit_then_event_ref() -> None:
    target = GitHubWebhookTarget(
        event="push",
        repository="octo/demo",
        head_sha=HEAD,
        installation_id=123,
        ref="refs/heads/main",
    )

    plan = build_github_checkout_plan(target)

    assert [(item.ref, item.expected_sha) for item in plan.candidates] == [
        (HEAD, HEAD),
        ("refs/heads/main", HEAD),
    ]


def test_checkout_rejects_invalid_repository_and_sha() -> None:
    with pytest.raises(GitHubCheckoutError):
        build_github_checkout_plan(
            GitHubWebhookTarget(
                event="push",
                repository="bad/repo/extra",
                head_sha=HEAD,
                installation_id=123,
            )
        )

    with pytest.raises(GitHubCheckoutError):
        build_github_checkout_plan(
            GitHubWebhookTarget(
                event="push",
                repository="octo/demo",
                head_sha="not-a-sha",
                installation_id=123,
            )
        )


def test_checkout_uses_secret_only_in_environment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan = build_github_checkout_plan(
        GitHubWebhookTarget(
            event="push",
            repository="octo/demo",
            head_sha=HEAD,
            installation_id=123,
        )
    )
    destination = tmp_path / "checkout"
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_which(name: str) -> str:
        assert name == "git"
        return "/usr/bin/git"

    def fake_run(
        args: list[str],
        *,
        env: dict[str, str],
        capture_output: bool,
        text: bool,
        check: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((args, env))
        if args[1:3] == ["init", "--quiet"]:
            destination.mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(args, 0, "", "")
        if "rev-parse" in args:
            return subprocess.CompletedProcess(args, 0, HEAD + "\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_checkout.shutil.which",
        fake_which,
    )
    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_checkout.subprocess.run",
        fake_run,
    )

    result = checkout_github_repository(
        plan,
        installation_token="ghs_super_secret",
        destination=destination,
    )

    assert result.commit_sha == HEAD
    assert result.fetched_ref == HEAD
    assert calls

    for args, env in calls:
        joined = " ".join(args)
        assert "ghs_super_secret" not in joined
        assert env["GIT_TERMINAL_PROMPT"] == "0"
        assert env["GIT_CONFIG_NOSYSTEM"] == "1"
        assert env["GIT_CONFIG_GLOBAL"]
        assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
        assert env["GIT_CONFIG_VALUE_0"] == "Authorization: Bearer ghs_super_secret"
        assert env["GIT_CONFIG_KEY_1"] == "core.hooksPath"


def test_checkout_rejects_ref_that_moved_since_webhook(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = GitHubWebhookTarget(
        event="push",
        repository="octo/demo",
        head_sha=HEAD,
        installation_id=123,
        ref="refs/heads/main",
    )
    plan = build_github_checkout_plan(target)
    destination = tmp_path / "checkout"
    other_sha = "c" * 40

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_checkout.shutil.which",
        lambda name: "/usr/bin/git",
    )

    def fake_run(
        args: list[str],
        *,
        env: dict[str, str],
        capture_output: bool,
        text: bool,
        check: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        if args[1:3] == ["init", "--quiet"]:
            destination.mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(args, 0, "", "")
        if "fetch" in args:
            return subprocess.CompletedProcess(args, 0, "", "")
        if "rev-parse" in args:
            return subprocess.CompletedProcess(args, 0, other_sha + "\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_checkout.subprocess.run",
        fake_run,
    )

    with pytest.raises(GitHubCheckoutError, match="exact webhook revision"):
        checkout_github_repository(
            plan,
            installation_token="token",
            destination=destination,
        )

    assert not destination.exists()
