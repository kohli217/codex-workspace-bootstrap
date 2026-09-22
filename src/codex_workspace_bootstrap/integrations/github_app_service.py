from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal

from .github import GitHubCheckResult, build_github_check
from .github_webhook import (
    GitHubWebhookError,
    GitHubWebhookTarget,
    normalize_github_webhook,
    should_run_github_preflight,
    verify_github_webhook_signature,
)
from ..preflight import build_preflight


GitHubAppEventDisposition = Literal["ping", "ignored", "scan"]


class GitHubWebhookAuthenticationError(PermissionError):
    """Raised when a GitHub webhook signature cannot be verified."""


class GitHubWebhookPayloadError(ValueError):
    """Raised when a webhook body is not a valid JSON object."""


@dataclass(frozen=True)
class GitHubAppEventDecision:
    disposition: GitHubAppEventDisposition
    target: GitHubWebhookTarget | None = None


def prepare_github_app_event(
    *,
    event_name: str,
    raw_body: bytes,
    signature_header: str | None,
    webhook_secret: str | bytes,
) -> GitHubAppEventDecision:
    """Verify, parse, and route a GitHub App webhook without network calls."""

    if not verify_github_webhook_signature(
        webhook_secret,
        raw_body,
        signature_header,
    ):
        raise GitHubWebhookAuthenticationError("invalid GitHub webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GitHubWebhookPayloadError("webhook body is not valid UTF-8 JSON") from exc

    if not isinstance(payload, dict):
        raise GitHubWebhookPayloadError("webhook JSON payload must be an object")

    if event_name == "ping":
        return GitHubAppEventDecision("ping")

    try:
        target = normalize_github_webhook(event_name, payload)
    except GitHubWebhookError:
        raise

    if not should_run_github_preflight(target):
        return GitHubAppEventDecision("ignored", target)

    return GitHubAppEventDecision("scan", target)


def build_github_app_check(
    root: Path,
    *,
    strict: bool = True,
    fail_on_integrity: bool = False,
    require_ready: bool = False,
    name: str = "CWB Preflight",
) -> GitHubCheckResult:
    """Build a GitHub App Check result using repository-only preflight semantics."""

    report = build_preflight(
        root,
        include_local_toolchain=False,
    )
    return build_github_check(
        report,
        strict=strict,
        fail_on_integrity=fail_on_integrity,
        require_ready=require_ready,
        name=name,
    )
