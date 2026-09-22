from __future__ import annotations

from dataclasses import dataclass


GITHUB_APP_REPOSITORY_PERMISSIONS: dict[str, str] = {
    "checks": "write",
    "contents": "read",
    "pull_requests": "read",
}

GITHUB_APP_WEBHOOK_EVENTS: tuple[str, ...] = (
    "pull_request",
    "push",
)


@dataclass(frozen=True)
class GitHubAppRegistration:
    repository_permissions: dict[str, str]
    webhook_events: tuple[str, ...]


def required_github_app_registration() -> GitHubAppRegistration:
    """Return the minimum GitHub App registration contract used by CWB."""

    return GitHubAppRegistration(
        repository_permissions=dict(GITHUB_APP_REPOSITORY_PERMISSIONS),
        webhook_events=GITHUB_APP_WEBHOOK_EVENTS,
    )
