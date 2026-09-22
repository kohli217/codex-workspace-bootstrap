import html
import json

import pytest

from codex_workspace_bootstrap.integrations.github_manifest import (
    GitHubManifestError,
    build_github_app_manifest,
    build_manifest_registration,
    manifest_conversion_url,
    parse_manifest_conversion_response,
    render_manifest_registration_form,
    verify_manifest_callback_state,
)


def test_manifest_uses_registration_contract_and_deployed_urls() -> None:
    manifest = build_github_app_manifest(
        base_url="https://cwb.example.com/",
    )

    assert manifest["name"] == "CWB Preflight Dev"
    assert manifest["url"] == "https://github.com/kohli217/codex-workspace-bootstrap"
    assert manifest["hook_attributes"] == {
        "url": "https://cwb.example.com/webhooks/github",
        "active": True,
    }
    assert manifest["redirect_url"] == "https://cwb.example.com/setup/github/callback"
    assert manifest["public"] is False
    assert manifest["default_permissions"] == {
        "checks": "write",
        "contents": "read",
        "pull_requests": "read",
    }
    assert manifest["default_events"] == ["pull_request", "push"]
    assert manifest["request_oauth_on_install"] is False


@pytest.mark.parametrize(
    "base_url",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://example.com/path?query=yes",
        "https://example.com/#fragment",
        "not-a-url",
    ],
)
def test_manifest_requires_clean_https_base_url(base_url: str) -> None:
    with pytest.raises(GitHubManifestError):
        build_github_app_manifest(base_url=base_url)


def test_registration_builds_post_target_and_compact_manifest() -> None:
    registration = build_manifest_registration(
        base_url="https://cwb.example.com",
        state="csrf state/+",
    )

    assert registration.action_url == (
        "https://github.com/settings/apps/new?state=csrf%20state%2F%2B"
    )
    assert json.loads(registration.manifest_json)["default_events"] == [
        "pull_request",
        "push",
    ]


def test_registration_generates_state_when_not_supplied() -> None:
    registration = build_manifest_registration(
        base_url="https://cwb.example.com",
    )

    assert len(registration.state) >= 32


def test_manifest_form_escapes_payload_and_action() -> None:
    registration = build_manifest_registration(
        base_url="https://cwb.example.com",
        name='CWB "Dev" <Test>',
        state="state&value",
    )

    rendered = render_manifest_registration_form(registration)

    assert 'method="post"' in rendered
    assert "https://github.com/settings/apps/new?state=state%26value" in rendered
    assert html.escape(registration.manifest_json, quote=True) in rendered
    assert '<input type="hidden" name="manifest"' in rendered


def test_manifest_callback_state_uses_exact_match() -> None:
    verify_manifest_callback_state(
        expected_state="expected",
        received_state="expected",
    )

    with pytest.raises(GitHubManifestError, match="does not match"):
        verify_manifest_callback_state(
            expected_state="expected",
            received_state="other",
        )

    with pytest.raises(GitHubManifestError, match="missing"):
        verify_manifest_callback_state(
            expected_state="expected",
            received_state=None,
        )


def test_manifest_conversion_url_escapes_code() -> None:
    assert manifest_conversion_url("abc/123+xyz") == (
        "https://api.github.com/app-manifests/abc%2F123%2Bxyz/conversions"
    )


def test_conversion_parser_keeps_secrets_out_of_repr_and_public_metadata() -> None:
    private_key = "-----BEGIN RSA PRIVATE KEY-----\nsecret\n-----END RSA PRIVATE KEY-----"
    credentials = parse_manifest_conversion_response(
        {
            "id": 123,
            "client_id": "Iv23liExample",
            "pem": private_key,
            "webhook_secret": "webhook-super-secret",
            "slug": "cwb-preflight-dev",
        }
    )

    assert credentials.app_id == 123
    assert credentials.client_id == "Iv23liExample"
    assert credentials.private_key_pem == private_key
    assert credentials.webhook_secret == "webhook-super-secret"
    assert credentials.public_metadata() == {
        "app_id": 123,
        "client_id": "Iv23liExample",
        "slug": "cwb-preflight-dev",
    }

    rendered = repr(credentials)
    assert "webhook-super-secret" not in rendered
    assert "BEGIN RSA PRIVATE KEY" not in rendered


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"id": 123, "client_id": "x", "pem": "bad", "webhook_secret": "secret"},
        {
            "id": 123,
            "client_id": "x",
            "pem": "-----BEGIN PRIVATE KEY-----x",
            "webhook_secret": "",
        },
    ],
)
def test_conversion_parser_rejects_incomplete_secret_payload(
    payload: dict[str, object],
) -> None:
    with pytest.raises(GitHubManifestError):
        parse_manifest_conversion_response(payload)
