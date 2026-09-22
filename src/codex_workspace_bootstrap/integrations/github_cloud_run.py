from __future__ import annotations

from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
import base64
import hmac
import html
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

from .github_app_service import (
    GitHubWebhookAuthenticationError,
    GitHubWebhookPayloadError,
    prepare_github_app_event,
)
from .github_manifest import (
    GitHubManifestCredentials,
    build_manifest_registration,
    manifest_conversion_url,
    parse_manifest_conversion_response,
    render_manifest_registration_form,
    verify_manifest_callback_state,
)
from .github_runtime import GitHubScanResult, execute_github_scan
from .github_webhook import GitHubWebhookError, GitHubWebhookTarget


MAX_WEBHOOK_BYTES = 25 * 1024 * 1024
MAX_CONTROL_RESPONSE_BYTES = 2 * 1024 * 1024
METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/token"
)
GITHUB_API_VERSION = "2026-03-10"
USER_AGENT = "codex-workspace-bootstrap"


class CloudRunAppError(RuntimeError):
    """Raised when the Cloud Run delivery shell cannot safely process a request."""


@dataclass(frozen=True)
class QueuedGitHubScan:
    delivery_id: str
    target: GitHubWebhookTarget


@dataclass(frozen=True)
class WebhookIngressResult:
    disposition: str
    delivery_id: str


def _bounded_json_response(response, *, limit: int = MAX_CONTROL_RESPONSE_BYTES) -> dict[str, object]:
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise CloudRunAppError("remote response exceeded size limit")
    if not raw:
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloudRunAppError("remote service returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise CloudRunAppError("remote service returned a non-object JSON response")
    return value


def google_metadata_access_token() -> str:
    request = Request(
        METADATA_TOKEN_URL,
        headers={"Metadata-Flavor": "Google"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=5) as response:
            body = _bounded_json_response(response)
    except (HTTPError, URLError) as exc:
        raise CloudRunAppError("could not obtain Google metadata access token") from exc

    token = body.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise CloudRunAppError("metadata response did not contain an access token")
    return token


def _google_json_request(
    *,
    method: str,
    url: str,
    access_token: str,
    body: dict[str, object],
) -> dict[str, object]:
    data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method=method,
    )
    try:
        with urlopen(request, timeout=20) as response:
            return _bounded_json_response(response)
    except HTTPError as exc:
        raise CloudRunAppError(
            f"Google API request failed with HTTP {exc.code}"
        ) from exc
    except URLError as exc:
        raise CloudRunAppError("Google API request failed") from exc


def encode_queued_scan(message: QueuedGitHubScan) -> bytes:
    payload = {
        "delivery_id": message.delivery_id,
        "target": asdict(message.target),
    }
    return json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CloudRunAppError(f"invalid queued field: {field}")
    return value


def decode_queued_scan(data: bytes) -> QueuedGitHubScan:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloudRunAppError("queued scan is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise CloudRunAppError("queued scan must be a JSON object")

    delivery_id = payload.get("delivery_id")
    if not isinstance(delivery_id, str) or not delivery_id.strip():
        raise CloudRunAppError("queued scan is missing delivery_id")

    target_payload = payload.get("target")
    if not isinstance(target_payload, dict):
        raise CloudRunAppError("queued scan is missing target")

    event = target_payload.get("event")
    repository = target_payload.get("repository")
    head_sha = target_payload.get("head_sha")
    installation_id = target_payload.get("installation_id")

    if event not in {"push", "pull_request"}:
        raise CloudRunAppError("queued scan has unsupported event")
    if not isinstance(repository, str) or not repository.strip():
        raise CloudRunAppError("queued scan is missing repository")
    if not isinstance(head_sha, str) or not head_sha.strip():
        raise CloudRunAppError("queued scan is missing head_sha")
    if (
        isinstance(installation_id, bool)
        or not isinstance(installation_id, int)
        or installation_id <= 0
    ):
        raise CloudRunAppError("queued scan is missing installation_id")

    pull_request_number = target_payload.get("pull_request_number")
    if pull_request_number is not None and (
        isinstance(pull_request_number, bool)
        or not isinstance(pull_request_number, int)
        or pull_request_number <= 0
    ):
        raise CloudRunAppError("queued scan has invalid pull_request_number")

    return QueuedGitHubScan(
        delivery_id=delivery_id,
        target=GitHubWebhookTarget(
            event=event,
            repository=repository,
            head_sha=head_sha,
            installation_id=installation_id,
            action=_optional_text(target_payload.get("action"), "action"),
            pull_request_number=pull_request_number,
            merge_commit_sha=_optional_text(
                target_payload.get("merge_commit_sha"),
                "merge_commit_sha",
            ),
            ref=_optional_text(target_payload.get("ref"), "ref"),
        ),
    )


def publish_queued_scan(
    message: QueuedGitHubScan,
    *,
    project_id: str,
    topic_id: str,
    access_token: str | None = None,
) -> str:
    if not project_id.strip() or not topic_id.strip():
        raise CloudRunAppError("Pub/Sub project and topic must not be empty")
    token = access_token or google_metadata_access_token()
    encoded = base64.b64encode(encode_queued_scan(message)).decode("ascii")
    response = _google_json_request(
        method="POST",
        url=(
            "https://pubsub.googleapis.com/v1/projects/"
            + quote(project_id, safe="")
            + "/topics/"
            + quote(topic_id, safe="")
            + ":publish"
        ),
        access_token=token,
        body={
            "messages": [
                {
                    "data": encoded,
                    "attributes": {
                        "github_delivery": message.delivery_id,
                    },
                }
            ]
        },
    )
    message_ids = response.get("messageIds")
    if (
        not isinstance(message_ids, list)
        or not message_ids
        or not isinstance(message_ids[0], str)
        or not message_ids[0].strip()
    ):
        raise CloudRunAppError("Pub/Sub publish response did not contain a message id")
    return message_ids[0]


def enqueue_github_webhook(
    *,
    event_name: str,
    delivery_id: str,
    raw_body: bytes,
    signature_header: str | None,
    webhook_secret: str | bytes,
    publish: Callable[[QueuedGitHubScan], object],
) -> WebhookIngressResult:
    if not delivery_id.strip():
        raise CloudRunAppError("GitHub webhook is missing X-GitHub-Delivery")

    decision = prepare_github_app_event(
        event_name=event_name,
        raw_body=raw_body,
        signature_header=signature_header,
        webhook_secret=webhook_secret,
    )
    if decision.disposition == "scan":
        if decision.target is None or decision.target.installation_id is None:
            raise CloudRunAppError("scan event is missing GitHub App installation_id")
        publish(
            QueuedGitHubScan(
                delivery_id=delivery_id,
                target=decision.target,
            )
        )
    return WebhookIngressResult(
        disposition=decision.disposition,
        delivery_id=delivery_id,
    )


def parse_pubsub_push(raw_body: bytes) -> QueuedGitHubScan:
    try:
        envelope = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloudRunAppError("Pub/Sub push body is not valid JSON") from exc
    if not isinstance(envelope, dict):
        raise CloudRunAppError("Pub/Sub push body must be a JSON object")
    message = envelope.get("message")
    if not isinstance(message, dict):
        raise CloudRunAppError("Pub/Sub push body is missing message")
    encoded = message.get("data")
    if not isinstance(encoded, str) or not encoded:
        raise CloudRunAppError("Pub/Sub push message is missing data")
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise CloudRunAppError("Pub/Sub push data is not valid base64") from exc
    return decode_queued_scan(decoded)


def run_queued_scan(
    message: QueuedGitHubScan,
    *,
    client_id: str,
    private_key_path: Path,
    execute: Callable[..., GitHubScanResult] = execute_github_scan,
) -> GitHubScanResult:
    return execute(
        message.target,
        client_id=client_id,
        private_key_path=private_key_path,
    )


def exchange_manifest_code(code: str) -> GitHubManifestCredentials:
    request = Request(
        manifest_conversion_url(code),
        data=b"",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = _bounded_json_response(response)
    except HTTPError as exc:
        raise CloudRunAppError(
            f"GitHub manifest conversion failed with HTTP {exc.code}"
        ) from exc
    except URLError as exc:
        raise CloudRunAppError("GitHub manifest conversion failed") from exc
    return parse_manifest_conversion_response(payload)


def add_secret_version(
    *,
    project_id: str,
    secret_id: str,
    value: str,
    access_token: str | None = None,
) -> None:
    if not project_id.strip() or not secret_id.strip():
        raise CloudRunAppError("Secret Manager project and secret id must not be empty")
    token = access_token or google_metadata_access_token()
    _google_json_request(
        method="POST",
        url=(
            "https://secretmanager.googleapis.com/v1/projects/"
            + quote(project_id, safe="")
            + "/secrets/"
            + quote(secret_id, safe="")
            + ":addVersion"
        ),
        access_token=token,
        body={
            "payload": {
                "data": base64.b64encode(value.encode("utf-8")).decode("ascii")
            }
        },
    )


def store_manifest_credentials(
    credentials: GitHubManifestCredentials,
    *,
    project_id: str,
    client_id_secret: str,
    private_key_secret: str,
    webhook_secret: str,
    access_token: str | None = None,
) -> None:
    token = access_token or google_metadata_access_token()
    add_secret_version(
        project_id=project_id,
        secret_id=client_id_secret,
        value=credentials.client_id,
        access_token=token,
    )
    add_secret_version(
        project_id=project_id,
        secret_id=private_key_secret,
        value=credentials.private_key_pem,
        access_token=token,
    )
    add_secret_version(
        project_id=project_id,
        secret_id=webhook_secret,
        value=credentials.webhook_secret,
        access_token=token,
    )


def _read_secret(path: str) -> str:
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise CloudRunAppError("required mounted secret is unavailable") from exc
    if not value:
        raise CloudRunAppError("required mounted secret is empty")
    return value


def _cookie_value(cookie_header: str | None, name: str) -> str | None:
    if not cookie_header:
        return None
    for item in cookie_header.split(";"):
        key, sep, value = item.strip().partition("=")
        if sep and key == name:
            return value
    return None


class CloudRunHandler(BaseHTTPRequestHandler):
    server_version = "CWBCloudRun/1"
    sys_version = ""

    def log_message(self, format: str, *args: object) -> None:
        # Avoid logging setup-token query strings or credentials.
        return

    def _send(
        self,
        status: int,
        body: bytes = b"",
        *,
        content_type: str = "application/json; charset=utf-8",
        headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_json(self, status: int, value: dict[str, object]) -> None:
        self._send(
            status,
            json.dumps(value, separators=(",", ":")).encode("utf-8"),
        )

    def _send_html(
        self,
        status: int,
        value: str,
        *,
        headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self._send(
            status,
            value.encode("utf-8"),
            content_type="text/html; charset=utf-8",
            headers=headers,
        )

    def _read_body(self, *, limit: int) -> bytes:
        value = self.headers.get("Content-Length")
        if value is None:
            raise CloudRunAppError("Content-Length is required")
        try:
            length = int(value)
        except ValueError as exc:
            raise CloudRunAppError("invalid Content-Length") from exc
        if length < 0 or length > limit:
            raise CloudRunAppError("request body exceeds size limit")
        return self.rfile.read(length)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._send_json(
                200,
                {"ok": True, "mode": os.environ.get("CWB_GITHUB_APP_MODE", "")},
            )
            return
        if parsed.path == "/setup/github":
            self._handle_setup(parsed)
            return
        if parsed.path == "/setup/github/callback":
            self._handle_setup_callback(parsed)
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        mode = os.environ.get("CWB_GITHUB_APP_MODE", "")
        if mode == "ingress" and parsed.path == "/webhooks/github":
            self._handle_webhook()
            return
        if mode == "worker" and parsed.path == "/pubsub/github-scan":
            self._handle_worker()
            return
        self._send_json(404, {"error": "not found"})

    def _setup_authorized(self) -> bool:
        expected = _read_secret(
            os.environ.get(
                "CWB_SETUP_TOKEN_PATH",
                "/var/run/secrets/cwb/setup-token",
            )
        )
        received = _cookie_value(self.headers.get("Cookie"), "cwb_setup")
        return received is not None and hmac.compare_digest(expected, received)

    def _handle_setup(self, parsed) -> None:
        if os.environ.get("CWB_GITHUB_APP_MODE") != "ingress":
            self._send_json(404, {"error": "not found"})
            return
        query = parse_qs(parsed.query)
        supplied = query.get("token", [None])[0]
        if supplied is not None:
            expected = _read_secret(
                os.environ.get(
                    "CWB_SETUP_TOKEN_PATH",
                    "/var/run/secrets/cwb/setup-token",
                )
            )
            if not hmac.compare_digest(expected, supplied):
                self._send_json(403, {"error": "forbidden"})
                return
            self._send(
                303,
                headers=(
                    ("Location", "/setup/github"),
                    (
                        "Set-Cookie",
                        "cwb_setup="
                        + supplied
                        + "; Path=/setup/github; Max-Age=3600; Secure; HttpOnly; SameSite=Lax",
                    ),
                ),
            )
            return
        if not self._setup_authorized():
            self._send_json(403, {"error": "forbidden"})
            return

        base_url = os.environ.get("CWB_PUBLIC_BASE_URL", "").rstrip("/")
        registration = build_manifest_registration(base_url=base_url)
        form = render_manifest_registration_form(registration)
        page = (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<title>CWB GitHub App Setup</title></head><body>"
            "<h1>CWB GitHub App Setup</h1>"
            "<p>Create the private development GitHub App using the preconfigured permissions.</p>"
            + form
            + "</body></html>"
        )
        self._send_html(
            200,
            page,
            headers=(
                (
                    "Set-Cookie",
                    "cwb_manifest_state="
                    + registration.state
                    + "; Path=/setup/github; Max-Age=3600; Secure; HttpOnly; SameSite=Lax",
                ),
            ),
        )

    def _handle_setup_callback(self, parsed) -> None:
        if os.environ.get("CWB_GITHUB_APP_MODE") != "ingress":
            self._send_json(404, {"error": "not found"})
            return
        if not self._setup_authorized():
            self._send_json(403, {"error": "forbidden"})
            return
        query = parse_qs(parsed.query)
        code = query.get("code", [None])[0]
        received_state = query.get("state", [None])[0]
        expected_state = _cookie_value(
            self.headers.get("Cookie"),
            "cwb_manifest_state",
        )
        try:
            verify_manifest_callback_state(
                expected_state=expected_state or "",
                received_state=received_state,
            )
            if code is None:
                raise CloudRunAppError("manifest callback code is missing")
            credentials = exchange_manifest_code(code)
            store_manifest_credentials(
                credentials,
                project_id=os.environ["CWB_GCP_PROJECT"],
                client_id_secret=os.environ["CWB_GITHUB_CLIENT_ID_SECRET"],
                private_key_secret=os.environ["CWB_GITHUB_PRIVATE_KEY_SECRET"],
                webhook_secret=os.environ["CWB_GITHUB_WEBHOOK_SECRET"],
            )
        except (CloudRunAppError, KeyError, ValueError) as exc:
            print(f"manifest callback failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            self._send_json(500, {"error": "GitHub App setup failed"})
            return

        metadata = credentials.public_metadata()
        page = (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<title>CWB GitHub App Created</title></head><body>"
            "<h1>GitHub App created</h1>"
            "<p>Credentials were stored directly in Secret Manager.</p>"
            "<p>App ID: "
            + html.escape(str(metadata["app_id"]))
            + "</p><p>Client ID: "
            + html.escape(str(metadata["client_id"]))
            + "</p><p>Slug: "
            + html.escape(str(metadata.get("slug") or ""))
            + "</p></body></html>"
        )
        self._send_html(
            200,
            page,
            headers=(
                (
                    "Set-Cookie",
                    "cwb_setup=; Path=/setup/github; Max-Age=0; Secure; HttpOnly; SameSite=Lax",
                ),
                (
                    "Set-Cookie",
                    "cwb_manifest_state=; Path=/setup/github; Max-Age=0; Secure; HttpOnly; SameSite=Lax",
                ),
            ),
        )

    def _handle_webhook(self) -> None:
        try:
            raw_body = self._read_body(limit=MAX_WEBHOOK_BYTES)
            secret = _read_secret(
                os.environ.get(
                    "CWB_GITHUB_WEBHOOK_SECRET_PATH",
                    "/var/run/secrets/cwb/webhook-secret",
                )
            )
            project_id = os.environ["CWB_GCP_PROJECT"]
            topic_id = os.environ["CWB_PUBSUB_TOPIC"]
            result = enqueue_github_webhook(
                event_name=self.headers.get("X-GitHub-Event", ""),
                delivery_id=self.headers.get("X-GitHub-Delivery", ""),
                raw_body=raw_body,
                signature_header=self.headers.get("X-Hub-Signature-256"),
                webhook_secret=secret,
                publish=lambda message: publish_queued_scan(
                    message,
                    project_id=project_id,
                    topic_id=topic_id,
                ),
            )
        except GitHubWebhookAuthenticationError:
            self._send_json(401, {"error": "invalid webhook signature"})
            return
        except (
            GitHubWebhookPayloadError,
            GitHubWebhookError,
            CloudRunAppError,
            KeyError,
        ) as exc:
            print(f"webhook rejected: {type(exc).__name__}: {exc}", file=sys.stderr)
            self._send_json(400, {"error": "invalid webhook"})
            return
        self._send_json(
            202,
            {
                "accepted": True,
                "disposition": result.disposition,
                "delivery_id": result.delivery_id,
            },
        )

    def _handle_worker(self) -> None:
        try:
            raw_body = self._read_body(limit=MAX_CONTROL_RESPONSE_BYTES)
            message = parse_pubsub_push(raw_body)
            client_id = _read_secret(
                os.environ.get(
                    "CWB_GITHUB_APP_CLIENT_ID_PATH",
                    "/var/run/secrets/cwb/client-id",
                )
            )
            private_key = Path(
                os.environ.get(
                    "CWB_GITHUB_APP_PRIVATE_KEY_PATH",
                    "/var/run/secrets/cwb/private-key",
                )
            )
            result = run_queued_scan(
                message,
                client_id=client_id,
                private_key_path=private_key,
            )
        except Exception as exc:
            # A non-2xx response asks Pub/Sub to retry the message.
            print(f"worker failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            self._send_json(500, {"error": "scan failed"})
            return
        self._send_json(
            200,
            {
                "ok": True,
                "delivery_id": message.delivery_id,
                "repository": result.repository,
                "commit_sha": result.commit_sha,
                "conclusion": result.conclusion,
                "check_run_id": result.check_run_id,
            },
        )


def main() -> int:
    mode = os.environ.get("CWB_GITHUB_APP_MODE", "")
    if mode not in {"ingress", "worker"}:
        raise CloudRunAppError(
            "CWB_GITHUB_APP_MODE must be 'ingress' or 'worker'"
        )
    try:
        port = int(os.environ.get("PORT", "8080"))
    except ValueError as exc:
        raise CloudRunAppError("PORT must be an integer") from exc
    server = ThreadingHTTPServer(("0.0.0.0", port), CloudRunHandler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
