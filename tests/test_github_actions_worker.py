import base64
import io
import json
from urllib.error import HTTPError

import pytest

from codex_workspace_bootstrap.integrations.github_actions_worker import (
    GitHubActionsWorkerError,
    decode_scan_payload,
    request_actions_oidc_token,
    request_installation_token,
)
from codex_workspace_bootstrap.integrations.github_webhook import GitHubWebhookTarget


def _encoded_payload() -> str:
    payload = {
        "delivery_id": "delivery-123",
        "broker_grant": "signed-webhook-grant",
        "target": {
            "event": "push",
            "repository": "octo/demo",
            "head_sha": "a" * 40,
            "installation_id": 1234,
            "action": None,
            "pull_request_number": None,
            "merge_commit_sha": None,
            "ref": "refs/heads/main",
        },
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def test_decode_scan_payload_round_trips_normalized_target() -> None:
    delivery_id, broker_grant, target = decode_scan_payload(_encoded_payload())

    assert delivery_id == "delivery-123"
    assert broker_grant == "signed-webhook-grant"
    assert target == GitHubWebhookTarget(
        event="push",
        repository="octo/demo",
        head_sha="a" * 40,
        installation_id=1234,
        ref="refs/heads/main",
    )


def test_decode_scan_payload_rejects_invalid_installation() -> None:
    raw = json.dumps(
        {
            "delivery_id": "delivery-123",
            "broker_grant": "signed-webhook-grant",
            "target": {
                "event": "push",
                "repository": "octo/demo",
                "head_sha": "a" * 40,
                "installation_id": None,
            },
        }
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    with pytest.raises(GitHubActionsWorkerError, match="installation_id"):
        decode_scan_payload(encoded)


def test_oidc_request_uses_custom_audience(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, size: int) -> bytes:
            return b'{"value":"oidc-token"}'

    def fake_urlopen(request, *, timeout: int):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_actions_worker.urlopen",
        fake_urlopen,
    )

    token = request_actions_oidc_token(
        audience="https://example.workers.dev/tokens/github",
        request_url="https://token.actions.githubusercontent.com/oidc?x=1",
        request_token="actions-request-token",
    )

    assert token == "oidc-token"
    request = captured["request"]
    assert "audience=https%3A%2F%2Fexample.workers.dev%2Ftokens%2Fgithub" in request.full_url
    assert request.get_header("Authorization") == "Bearer actions-request-token"
    assert captured["timeout"] == 20


def test_installation_token_broker_request_is_scoped_to_target(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, size: int) -> bytes:
            return b'{"token":"ghs_short_lived"}'

    def fake_urlopen(request, *, timeout: int):
        captured["request"] = request
        return FakeResponse()

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_actions_worker.urlopen",
        fake_urlopen,
    )

    token = request_installation_token(
        endpoint="https://example.workers.dev/tokens/github",
        oidc_token="oidc-token",
        delivery_id="delivery-123",
        broker_grant="signed-webhook-grant",
        target=GitHubWebhookTarget(
            event="push",
            repository="octo/demo",
            head_sha="a" * 40,
            installation_id=1234,
        ),
    )

    assert token == "ghs_short_lived"
    request = captured["request"]
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer oidc-token"
    assert json.loads(request.data) == {
        "delivery_id": "delivery-123",
        "broker_grant": "signed-webhook-grant",
        "target": {
            "event": "push",
            "repository": "octo/demo",
            "head_sha": "a" * 40,
            "installation_id": 1234,
            "action": None,
            "pull_request_number": None,
            "merge_commit_sha": None,
            "ref": None,
        },
    }


def test_token_broker_error_does_not_include_response_body(monkeypatch) -> None:
    def fake_urlopen(request, *, timeout: int):
        raise HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"token":"must-not-leak"}'),
        )

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_actions_worker.urlopen",
        fake_urlopen,
    )

    with pytest.raises(GitHubActionsWorkerError) as exc_info:
        request_installation_token(
            endpoint="https://example.workers.dev/tokens/github",
            oidc_token="oidc-token",
            delivery_id="delivery-123",
            broker_grant="signed-webhook-grant",
            target=GitHubWebhookTarget(
                event="push",
                repository="octo/demo",
                head_sha="a" * 40,
                installation_id=1234,
            ),
        )

    assert "401" in str(exc_info.value)
    assert "must-not-leak" not in str(exc_info.value)


def test_decode_scan_payload_requires_broker_grant() -> None:
    raw = json.dumps(
        {
            "delivery_id": "delivery-123",
            "target": {
                "event": "push",
                "repository": "octo/demo",
                "head_sha": "a" * 40,
                "installation_id": 1234,
            },
        }
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    with pytest.raises(GitHubActionsWorkerError, match="broker_grant"):
        decode_scan_payload(encoded)
