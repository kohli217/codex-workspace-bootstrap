from __future__ import annotations

import argparse
import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .github_runtime import (
    GitHubAppRuntimeError,
    GitHubScanResult,
    execute_github_scan_with_token,
)
from .github_webhook import GitHubWebhookTarget


_MAX_RESPONSE_BYTES = 1024 * 1024


class GitHubActionsWorkerError(RuntimeError):
    """Raised when the free GitHub Actions worker cannot authenticate or run."""


def _base64url_decode(value: str) -> bytes:
    if not value.strip():
        raise GitHubActionsWorkerError("scan payload must not be empty")
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise GitHubActionsWorkerError("scan payload is not valid base64url") from exc


def decode_scan_payload(encoded: str) -> tuple[str, GitHubWebhookTarget]:
    try:
        payload = json.loads(_base64url_decode(encoded).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GitHubActionsWorkerError("scan payload is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise GitHubActionsWorkerError("scan payload must be a JSON object")

    delivery_id = payload.get("delivery_id")
    target = payload.get("target")
    if not isinstance(delivery_id, str) or not delivery_id.strip():
        raise GitHubActionsWorkerError("scan payload is missing delivery_id")
    if not isinstance(target, dict):
        raise GitHubActionsWorkerError("scan payload is missing target")

    event = target.get("event")
    repository = target.get("repository")
    head_sha = target.get("head_sha")
    installation_id = target.get("installation_id")
    if event not in {"push", "pull_request"}:
        raise GitHubActionsWorkerError("scan payload has unsupported event")
    if not isinstance(repository, str) or repository.count("/") != 1:
        raise GitHubActionsWorkerError("scan payload has invalid repository")
    if not isinstance(head_sha, str) or not head_sha.strip():
        raise GitHubActionsWorkerError("scan payload is missing head_sha")
    if (
        isinstance(installation_id, bool)
        or not isinstance(installation_id, int)
        or installation_id <= 0
    ):
        raise GitHubActionsWorkerError("scan payload is missing installation_id")

    number = target.get("pull_request_number")
    if number is not None and (
        isinstance(number, bool)
        or not isinstance(number, int)
        or number <= 0
    ):
        raise GitHubActionsWorkerError("scan payload has invalid pull_request_number")

    def optional_text(name: str) -> str | None:
        value = target.get(name)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise GitHubActionsWorkerError(f"scan payload has invalid {name}")
        return value

    return delivery_id, GitHubWebhookTarget(
        event=event,
        repository=repository,
        head_sha=head_sha,
        installation_id=installation_id,
        action=optional_text("action"),
        pull_request_number=number,
        merge_commit_sha=optional_text("merge_commit_sha"),
        ref=optional_text("ref"),
    )


def _read_json_response(response) -> dict[str, object]:
    raw = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise GitHubActionsWorkerError("remote response exceeded size limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GitHubActionsWorkerError("remote service returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise GitHubActionsWorkerError("remote service returned non-object JSON")
    return value


def request_actions_oidc_token(
    *,
    audience: str,
    request_url: str | None = None,
    request_token: str | None = None,
) -> str:
    url = request_url or os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    bearer = request_token or os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not url or not bearer:
        raise GitHubActionsWorkerError(
            "GitHub Actions OIDC environment is unavailable; id-token: write is required"
        )

    separator = "&" if "?" in url else "?"
    request = Request(
        url + separator + urlencode({"audience": audience}),
        headers={"Authorization": f"Bearer {bearer}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=20) as response:
            body = _read_json_response(response)
    except HTTPError as exc:
        raise GitHubActionsWorkerError(
            f"GitHub Actions OIDC request failed with HTTP {exc.code}"
        ) from exc
    except URLError as exc:
        raise GitHubActionsWorkerError("GitHub Actions OIDC request failed") from exc

    value = body.get("value")
    if not isinstance(value, str) or not value.strip():
        raise GitHubActionsWorkerError("GitHub Actions OIDC response is missing value")
    return value


def _validated_token_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise GitHubActionsWorkerError(
            "token endpoint must be an absolute HTTPS URL without credentials, query, or fragment"
        )
    return endpoint.rstrip("/")


def request_installation_token(
    *,
    endpoint: str,
    oidc_token: str,
    target: GitHubWebhookTarget,
) -> str:
    if target.installation_id is None:
        raise GitHubActionsWorkerError("scan target is missing installation_id")
    url = _validated_token_endpoint(endpoint)
    request = Request(
        url,
        data=json.dumps(
            {
                "repository": target.repository,
                "installation_id": target.installation_id,
            },
            separators=(",", ":"),
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {oidc_token}",
            "Content-Type": "application/json",
            "User-Agent": "codex-workspace-bootstrap",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            body = _read_json_response(response)
    except HTTPError as exc:
        raise GitHubActionsWorkerError(
            f"installation-token broker returned HTTP {exc.code}"
        ) from exc
    except URLError as exc:
        raise GitHubActionsWorkerError(
            "installation-token broker request failed"
        ) from exc

    token = body.get("token")
    if not isinstance(token, str) or not token.strip():
        raise GitHubActionsWorkerError(
            "installation-token broker response is missing token"
        )
    return token


def execute_actions_scan(
    *,
    encoded_payload: str,
    token_endpoint: str,
) -> GitHubScanResult:
    delivery_id, target = decode_scan_payload(encoded_payload)
    audience = _validated_token_endpoint(token_endpoint)
    oidc_token = request_actions_oidc_token(audience=audience)
    installation_token = request_installation_token(
        endpoint=audience,
        oidc_token=oidc_token,
        target=target,
    )
    return execute_github_scan_with_token(
        target,
        installation_token=installation_token,
        external_id=delivery_id,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--payload",
        default=os.environ.get("CWB_SCAN_PAYLOAD", ""),
        help="base64url-encoded normalized GitHub scan target",
    )
    parser.add_argument(
        "--token-endpoint",
        default=os.environ.get("CWB_TOKEN_ENDPOINT", ""),
        help="Cloudflare HTTPS installation-token broker endpoint",
    )
    args = parser.parse_args(argv)

    try:
        result = execute_actions_scan(
            encoded_payload=args.payload,
            token_endpoint=args.token_endpoint,
        )
    except (GitHubActionsWorkerError, GitHubAppRuntimeError) as exc:
        print(f"CWB GitHub App scan failed: {exc}")
        return 1

    suffix = " (deduplicated)" if result.deduplicated else ""
    print(
        f"CWB GitHub App scan: {result.repository}@{result.commit_sha} "
        f"-> {result.conclusion}{suffix}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
