from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Mapping, object as _object  # type: ignore[attr-defined]


SUPPORTED_PULL_REQUEST_ACTIONS = frozenset(
    {
        "opened",
        "reopened",
        "synchronize",
        "ready_for_review",
    }
)


class GitHubWebhookError(ValueError):
    """Raised when a supported GitHub webhook cannot be normalized safely."""


@dataclass(frozen=True)
class GitHubWebhookTarget:
    event: str
    repository: str
    head_sha: str
    installation_id: int | None
    action: str | None = None
    pull_request_number: int | None = None
    ref: str | None = None


def verify_github_webhook_signature(
    secret: str | bytes,
    body: bytes,
    signature_header: str | None,
) -> bool:
    """Verify GitHub's X-Hub-Signature-256 value using constant-time comparison."""

    if signature_header is None or not signature_header.startswith("sha256="):
        return False

    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
    expected = "sha256=" + hmac.new(secret_bytes, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GitHubWebhookError(f"missing or invalid webhook object: {field}")
    return value


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GitHubWebhookError(f"missing or invalid webhook field: {field}")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)


def _installation_id(payload: Mapping[str, object]) -> int | None:
    installation = payload.get("installation")
    if installation is None:
        return None
    installation_map = _mapping(installation, "installation")
    value = installation_map.get("id")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GitHubWebhookError("missing or invalid webhook field: installation.id")
    return value


def normalize_github_webhook(
    event_name: str,
    payload: Mapping[str, object],
) -> GitHubWebhookTarget:
    """Normalize supported webhook payloads into the commit that should be scanned."""

    repository = _mapping(payload.get("repository"), "repository")
    repository_name = _required_text(repository.get("full_name"), "repository.full_name")
    installation_id = _installation_id(payload)

    if event_name == "pull_request":
        pull_request = _mapping(payload.get("pull_request"), "pull_request")
        head = _mapping(pull_request.get("head"), "pull_request.head")
        head_sha = _required_text(head.get("sha"), "pull_request.head.sha")
        action = _optional_text(payload.get("action"), "action")

        number = payload.get("number")
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise GitHubWebhookError("missing or invalid webhook field: number")

        return GitHubWebhookTarget(
            event=event_name,
            repository=repository_name,
            head_sha=head_sha,
            installation_id=installation_id,
            action=action,
            pull_request_number=number,
        )

    if event_name == "push":
        head_sha = _required_text(payload.get("after"), "after")
        if set(head_sha) == {"0"}:
            raise GitHubWebhookError("deleted-ref push has no commit to scan")

        return GitHubWebhookTarget(
            event=event_name,
            repository=repository_name,
            head_sha=head_sha,
            installation_id=installation_id,
            ref=_optional_text(payload.get("ref"), "ref"),
        )

    raise GitHubWebhookError(f"unsupported GitHub webhook event: {event_name}")


def should_run_github_preflight(target: GitHubWebhookTarget) -> bool:
    """Return whether the normalized event should trigger a repository preflight."""

    if target.event == "push":
        return True
    if target.event == "pull_request":
        return target.action in SUPPORTED_PULL_REQUEST_ACTIONS
    return False
