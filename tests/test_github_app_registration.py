from codex_workspace_bootstrap.integrations.github_app import (
    GITHUB_APP_REPOSITORY_PERMISSIONS,
    GITHUB_APP_WEBHOOK_EVENTS,
    required_github_app_registration,
)


def test_github_app_registration_uses_minimum_repository_permissions() -> None:
    assert GITHUB_APP_REPOSITORY_PERMISSIONS == {
        "checks": "write",
        "contents": "read",
        "pull_requests": "read",
    }


def test_github_app_registration_subscribes_only_to_scan_events() -> None:
    assert GITHUB_APP_WEBHOOK_EVENTS == (
        "pull_request",
        "push",
    )


def test_registration_factory_returns_defensive_permission_copy() -> None:
    first = required_github_app_registration()
    second = required_github_app_registration()

    first.repository_permissions["contents"] = "write"

    assert second.repository_permissions == {
        "checks": "write",
        "contents": "read",
        "pull_requests": "read",
    }
    assert second.webhook_events == ("pull_request", "push")
