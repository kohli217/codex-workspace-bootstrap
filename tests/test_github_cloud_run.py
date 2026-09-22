import base64
import hashlib
import hmac
import json
from pathlib import Path

import pytest

from codex_workspace_bootstrap.integrations.github_cloud_run import (
    CloudRunAppError,
    QueuedGitHubScan,
    decode_queued_scan,
    encode_queued_scan,
    enqueue_github_webhook,
    parse_pubsub_push,
    publish_queued_scan,
    run_queued_scan,
    store_manifest_credentials,
    _safe_header_value,
)
from codex_workspace_bootstrap.integrations.github_manifest import (
    GitHubManifestCredentials,
)
from codex_workspace_bootstrap.integrations.github_runtime import GitHubScanResult
from codex_workspace_bootstrap.integrations.github_webhook import GitHubWebhookTarget


HEAD = "a" * 40
MERGE = "b" * 40


def _signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


def _queued() -> QueuedGitHubScan:
    return QueuedGitHubScan(
        delivery_id="delivery-123",
        target=GitHubWebhookTarget(
            event="pull_request",
            repository="octo/demo",
            head_sha=HEAD,
            installation_id=1234,
            action="synchronize",
            pull_request_number=42,
            merge_commit_sha=MERGE,
        ),
    )


def test_queue_message_round_trip_preserves_webhook_target() -> None:
    message = _queued()

    decoded = decode_queued_scan(encode_queued_scan(message))

    assert decoded == message


def test_decode_queue_rejects_missing_installation() -> None:
    payload = json.loads(encode_queued_scan(_queued()))
    payload["target"]["installation_id"] = None

    with pytest.raises(CloudRunAppError, match="installation_id"):
        decode_queued_scan(
            json.dumps(payload).encode("utf-8")
        )


def test_parse_pubsub_push_decodes_queue_message() -> None:
    message = _queued()
    body = json.dumps(
        {
            "message": {
                "messageId": "pubsub-1",
                "data": base64.b64encode(
                    encode_queued_scan(message)
                ).decode("ascii"),
            },
            "subscription": "projects/example/subscriptions/cwb",
        }
    ).encode("utf-8")

    assert parse_pubsub_push(body) == message


def test_parse_pubsub_push_rejects_invalid_base64() -> None:
    body = b'{"message":{"data":"***not-base64***"}}'

    with pytest.raises(CloudRunAppError, match="base64"):
        parse_pubsub_push(body)


def test_ingress_enqueues_only_scan_events() -> None:
    secret = "webhook-secret"
    body = (
        b'{"action":"synchronize","number":42,'
        b'"repository":{"full_name":"octo/demo"},'
        b'"installation":{"id":1234},'
        b'"pull_request":{"head":{"sha":"' + HEAD.encode("ascii") + b'"},'
        b'"merge_commit_sha":"' + MERGE.encode("ascii") + b'"}}'
    )
    published: list[QueuedGitHubScan] = []

    result = enqueue_github_webhook(
        event_name="pull_request",
        delivery_id="delivery-123",
        raw_body=body,
        signature_header=_signature(secret, body),
        webhook_secret=secret,
        publish=published.append,
    )

    assert result.disposition == "scan"
    assert published == [_queued()]


def test_ingress_does_not_publish_ignored_pull_request_action() -> None:
    secret = "webhook-secret"
    body = (
        b'{"action":"closed","number":42,'
        b'"repository":{"full_name":"octo/demo"},'
        b'"installation":{"id":1234},'
        b'"pull_request":{"head":{"sha":"' + HEAD.encode("ascii") + b'"}}}'
    )
    published: list[QueuedGitHubScan] = []

    result = enqueue_github_webhook(
        event_name="pull_request",
        delivery_id="delivery-ignored",
        raw_body=body,
        signature_header=_signature(secret, body),
        webhook_secret=secret,
        publish=published.append,
    )

    assert result.disposition == "ignored"
    assert published == []


def test_publish_queued_scan_uses_small_normalized_pubsub_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_request(*, method, url, access_token, body):
        captured.update(
            method=method,
            url=url,
            access_token=access_token,
            body=body,
        )
        return {"messageIds": ["msg-123"]}

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_cloud_run._google_json_request",
        fake_request,
    )

    message_id = publish_queued_scan(
        _queued(),
        project_id="demo-project",
        topic_id="cwb-github-scans",
        access_token="google-token",
    )

    assert message_id == "msg-123"
    assert captured["method"] == "POST"
    assert captured["access_token"] == "google-token"
    body = captured["body"]
    assert isinstance(body, dict)
    encoded = body["messages"][0]["data"]
    decoded = decode_queued_scan(base64.b64decode(encoded))
    assert decoded == _queued()


def test_store_manifest_credentials_writes_three_secret_versions(monkeypatch) -> None:
    credentials = GitHubManifestCredentials(
        app_id=123,
        client_id="Iv23liExample",
        private_key_pem="-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----",
        webhook_secret="webhook-secret",
        slug="cwb-preflight-dev",
    )
    calls: list[tuple[str, str]] = []

    def fake_add_secret_version(
        *,
        project_id: str,
        secret_id: str,
        value: str,
        access_token: str | None = None,
    ) -> None:
        assert project_id == "demo-project"
        assert access_token == "google-token"
        calls.append((secret_id, value))

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_cloud_run.add_secret_version",
        fake_add_secret_version,
    )

    store_manifest_credentials(
        credentials,
        project_id="demo-project",
        client_id_secret="client-id",
        private_key_secret="private-key",
        webhook_secret="webhook-secret",
        access_token="google-token",
    )

    assert calls == [
        ("client-id", "Iv23liExample"),
        (
            "private-key",
            "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----",
        ),
        ("webhook-secret", "webhook-secret"),
    ]


def test_run_queued_scan_passes_target_and_runtime_credentials(tmp_path: Path) -> None:
    message = _queued()
    key = tmp_path / "app.pem"
    key.write_text("key", encoding="utf-8")
    seen: dict[str, object] = {}

    def fake_execute(
        target,
        *,
        client_id: str,
        private_key_path: Path,
    ) -> GitHubScanResult:
        seen["target"] = target
        seen["client_id"] = client_id
        seen["private_key_path"] = private_key_path
        return GitHubScanResult(
            repository=target.repository,
            commit_sha=target.merge_commit_sha or target.head_sha,
            conclusion="success",
            check_run_id=987,
        )

    result = run_queued_scan(
        message,
        client_id="Iv23liExample",
        private_key_path=key,
        execute=fake_execute,
    )

    assert seen["target"] == message.target
    assert seen["client_id"] == "Iv23liExample"
    assert seen["private_key_path"] == key
    assert result.check_run_id == 987



def test_response_header_values_reject_line_breaks() -> None:
    assert _safe_header_value("safe-value") == "safe-value"

    with pytest.raises(CloudRunAppError, match="line break"):
        _safe_header_value("unsafe\r\nInjected: yes")
