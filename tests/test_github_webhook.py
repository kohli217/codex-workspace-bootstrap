import hashlib
import hmac

import pytest

from codex_workspace_bootstrap.integrations.github_webhook import (
    GitHubWebhookError,
    normalize_github_webhook,
    should_run_github_preflight,
    verify_github_webhook_signature,
)


def test_verify_github_webhook_signature_accepts_valid_digest() -> None:
    secret = "test-secret"
    body = b'{"zen":"keep it logically awesome"}'
    signature = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    assert verify_github_webhook_signature(secret, body, signature) is True


@pytest.mark.parametrize(
    "signature",
    [
        None,
        "",
        "sha1=deadbeef",
        "sha256=deadbeef",
    ],
)
def test_verify_github_webhook_signature_rejects_invalid_values(
    signature: str | None,
) -> None:
    assert verify_github_webhook_signature("secret", b"payload", signature) is False


def test_normalize_pull_request_webhook() -> None:
    target = normalize_github_webhook(
        "pull_request",
        {
            "action": "synchronize",
            "number": 42,
            "repository": {"full_name": "octo/demo"},
            "installation": {"id": 1234},
            "pull_request": {
                "head": {"sha": "abc123"},
                "merge_commit_sha": "def456",
            },
        },
    )

    assert target.event == "pull_request"
    assert target.repository == "octo/demo"
    assert target.head_sha == "abc123"
    assert target.installation_id == 1234
    assert target.action == "synchronize"
    assert target.pull_request_number == 42
    assert target.merge_commit_sha == "def456"
    assert target.ref is None
    assert should_run_github_preflight(target) is True


def test_normalize_push_webhook() -> None:
    target = normalize_github_webhook(
        "push",
        {
            "after": "def456",
            "ref": "refs/heads/main",
            "repository": {"full_name": "octo/demo"},
            "installation": {"id": 1234},
        },
    )

    assert target.event == "push"
    assert target.repository == "octo/demo"
    assert target.head_sha == "def456"
    assert target.installation_id == 1234
    assert target.action is None
    assert target.pull_request_number is None
    assert target.ref == "refs/heads/main"
    assert should_run_github_preflight(target) is True


@pytest.mark.parametrize(
    "action",
    ["opened", "reopened", "synchronize", "ready_for_review"],
)
def test_supported_pull_request_actions_trigger_preflight(action: str) -> None:
    target = normalize_github_webhook(
        "pull_request",
        {
            "action": action,
            "number": 7,
            "repository": {"full_name": "octo/demo"},
            "pull_request": {"head": {"sha": "abc123"}},
        },
    )

    assert should_run_github_preflight(target) is True


@pytest.mark.parametrize("action", ["closed", "labeled", "unlabeled", "converted_to_draft"])
def test_non_scan_pull_request_actions_do_not_trigger_preflight(action: str) -> None:
    target = normalize_github_webhook(
        "pull_request",
        {
            "action": action,
            "number": 7,
            "repository": {"full_name": "octo/demo"},
            "pull_request": {"head": {"sha": "abc123"}},
        },
    )

    assert should_run_github_preflight(target) is False


def test_deleted_ref_push_is_rejected() -> None:
    with pytest.raises(GitHubWebhookError, match="deleted-ref"):
        normalize_github_webhook(
            "push",
            {
                "after": "0" * 40,
                "ref": "refs/heads/old",
                "repository": {"full_name": "octo/demo"},
            },
        )


def test_unsupported_event_is_rejected() -> None:
    with pytest.raises(GitHubWebhookError, match="unsupported GitHub webhook event"):
        normalize_github_webhook(
            "issues",
            {
                "repository": {"full_name": "octo/demo"},
            },
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"repository": {}},
        {"repository": {"full_name": "octo/demo"}, "number": 1, "pull_request": {}},
        {
            "repository": {"full_name": "octo/demo"},
            "number": 1,
            "pull_request": {"head": {}},
        },
    ],
)
def test_malformed_pull_request_payload_is_rejected(
    payload: dict[str, object],
) -> None:
    with pytest.raises(GitHubWebhookError):
        normalize_github_webhook("pull_request", payload)
