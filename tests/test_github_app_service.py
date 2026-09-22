import hashlib
import hmac
from pathlib import Path
import shutil
import subprocess

import pytest

from codex_workspace_bootstrap.integrations.github_app_service import (
    GitHubWebhookAuthenticationError,
    GitHubWebhookPayloadError,
    build_github_app_check,
    prepare_github_app_event,
)


def _signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


def test_prepare_github_app_event_accepts_ping() -> None:
    secret = "webhook-secret"
    body = b'{"zen":"keep it logically awesome"}'

    decision = prepare_github_app_event(
        event_name="ping",
        raw_body=body,
        signature_header=_signature(secret, body),
        webhook_secret=secret,
    )

    assert decision.disposition == "ping"
    assert decision.target is None


def test_prepare_github_app_event_routes_scan_event() -> None:
    secret = "webhook-secret"
    body = (
        b'{"action":"synchronize","number":7,'
        b'"repository":{"full_name":"octo/demo"},'
        b'"installation":{"id":1234},'
        b'"pull_request":{"head":{"sha":"abc123"}}}'
    )

    decision = prepare_github_app_event(
        event_name="pull_request",
        raw_body=body,
        signature_header=_signature(secret, body),
        webhook_secret=secret,
    )

    assert decision.disposition == "scan"
    assert decision.target is not None
    assert decision.target.repository == "octo/demo"
    assert decision.target.head_sha == "abc123"
    assert decision.target.installation_id == 1234


def test_prepare_github_app_event_routes_non_scan_pr_action_to_ignored() -> None:
    secret = "webhook-secret"
    body = (
        b'{"action":"closed","number":7,'
        b'"repository":{"full_name":"octo/demo"},'
        b'"pull_request":{"head":{"sha":"abc123"}}}'
    )

    decision = prepare_github_app_event(
        event_name="pull_request",
        raw_body=body,
        signature_header=_signature(secret, body),
        webhook_secret=secret,
    )

    assert decision.disposition == "ignored"
    assert decision.target is not None
    assert decision.target.action == "closed"


def test_prepare_github_app_event_rejects_invalid_signature() -> None:
    with pytest.raises(
        GitHubWebhookAuthenticationError,
        match="invalid GitHub webhook signature",
    ):
        prepare_github_app_event(
            event_name="ping",
            raw_body=b'{"zen":"hello"}',
            signature_header="sha256=invalid",
            webhook_secret="webhook-secret",
        )


@pytest.mark.parametrize(
    "body",
    [
        b"{not-json",
        b"[]",
    ],
)
def test_prepare_github_app_event_rejects_invalid_payload(body: bytes) -> None:
    secret = "webhook-secret"

    with pytest.raises(GitHubWebhookPayloadError):
        prepare_github_app_event(
            event_name="ping",
            raw_body=body,
            signature_header=_signature(secret, body),
            webhook_secret=secret,
        )


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_build_github_app_check_always_uses_repository_only_preflight(
    tmp_path: Path,
    monkeypatch,
) -> None:
    subprocess.run(
        ("git", "-C", str(tmp_path), "init"),
        check=True,
        capture_output=True,
        text=True,
    )
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"packageManager":"pnpm@10","scripts":{"test":"vitest"}}',
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Run §pnpm test§.\n".replace("§", "`"), encoding="utf-8")

    def fail_tool_check(label: str, command: tuple[str, ...]):
        raise AssertionError(f"local tool check should not run: {label} {command}")

    monkeypatch.setattr("codex_workspace_bootstrap.audit._tool_check", fail_tool_check)

    check = build_github_app_check(tmp_path)

    assert check.conclusion == "success"
    assert check.title == "CWB preflight: READY"
    assert "**Local toolchain checks:** skipped (repository-only mode)" in check.summary
