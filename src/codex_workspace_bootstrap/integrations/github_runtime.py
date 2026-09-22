from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .github_app_service import build_github_app_check
from .github_checkout import (
    build_github_checkout_plan,
    checkout_github_repository,
)
from .github_delivery import (
    GitHubApiRequest,
    build_check_run_request,
    build_github_app_jwt,
    build_installation_token_request,
)
from .github_webhook import GitHubWebhookTarget


_MAX_GITHUB_RESPONSE_BYTES = 2 * 1024 * 1024


class GitHubAppRuntimeError(RuntimeError):
    """Raised when the GitHub App worker cannot complete a scan safely."""


@dataclass(frozen=True)
class GitHubApiResponse:
    status: int
    body: dict[str, object]


@dataclass(frozen=True)
class GitHubScanResult:
    repository: str
    commit_sha: str
    conclusion: str
    check_run_id: int | None = None
    check_run_url: str | None = None


def openssl_rs256_sign(
    private_key_path: Path,
    signing_input: bytes,
) -> bytes:
    """Sign JWT input with the GitHub App private key using OpenSSL RS256."""

    key = private_key_path.expanduser().resolve()
    if not key.is_file():
        raise GitHubAppRuntimeError("GitHub App private key file does not exist")
    if shutil.which("openssl") is None:
        raise GitHubAppRuntimeError("openssl command is required for GitHub App signing")

    completed = subprocess.run(
        (
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(key),
        ),
        input=signing_input,
        capture_output=True,
        check=False,
        timeout=15,
    )
    if completed.returncode != 0 or not completed.stdout:
        raise GitHubAppRuntimeError("OpenSSL could not sign the GitHub App JWT")
    return completed.stdout


def send_github_api_request(
    request: GitHubApiRequest,
    *,
    timeout: int = 20,
) -> GitHubApiResponse:
    """Execute one bounded GitHub REST request using only the Python stdlib."""

    headers = dict(request.headers)
    data: bytes | None = None
    if request.json_body is not None:
        data = json.dumps(
            request.json_body,
            separators=(",", ":"),
        ).encode("utf-8")
        headers["Content-Type"] = "application/json"

    http_request = Request(
        request.url,
        data=data,
        headers=headers,
        method=request.method,
    )

    try:
        with urlopen(http_request, timeout=timeout) as response:
            raw = response.read(_MAX_GITHUB_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_GITHUB_RESPONSE_BYTES:
                raise GitHubAppRuntimeError("GitHub API response exceeded size limit")
            status = int(response.status)
    except HTTPError as exc:
        raise GitHubAppRuntimeError(
            f"GitHub API request failed with HTTP {exc.code}"
        ) from exc
    except URLError as exc:
        raise GitHubAppRuntimeError("GitHub API request failed") from exc

    if not raw:
        body: object = {}
    else:
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubAppRuntimeError(
                "GitHub API returned invalid JSON"
            ) from exc

    if not isinstance(body, dict):
        raise GitHubAppRuntimeError("GitHub API response must be a JSON object")

    return GitHubApiResponse(status=status, body=body)


def installation_token_from_response(response: GitHubApiResponse) -> str:
    """Extract an installation token without assuming a token length or format."""

    if response.status != 201:
        raise GitHubAppRuntimeError(
            f"installation token request returned HTTP {response.status}"
        )

    token = response.body.get("token")
    if not isinstance(token, str) or not token.strip():
        raise GitHubAppRuntimeError(
            "installation token response did not contain a token"
        )
    return token


def _check_run_metadata(
    response: GitHubApiResponse,
) -> tuple[int | None, str | None]:
    if response.status != 201:
        raise GitHubAppRuntimeError(
            f"Check Run request returned HTTP {response.status}"
        )

    check_id = response.body.get("id")
    if isinstance(check_id, bool) or not isinstance(check_id, int):
        check_id = None

    html_url = response.body.get("html_url")
    if not isinstance(html_url, str) or not html_url.strip():
        html_url = None

    return check_id, html_url


def execute_github_scan(
    target: GitHubWebhookTarget,
    *,
    client_id: str,
    private_key_path: Path,
    workspace_parent: Path | None = None,
    now: int | None = None,
    send_request: Callable[[GitHubApiRequest], GitHubApiResponse] = send_github_api_request,
) -> GitHubScanResult:
    """Run one already-verified webhook scan as a queue/worker operation."""

    installation_id = target.installation_id
    if installation_id is None:
        raise GitHubAppRuntimeError(
            "GitHub App webhook target is missing installation_id"
        )

    unix_time = int(time.time()) if now is None else now
    app_jwt = build_github_app_jwt(
        client_id=client_id,
        now=unix_time,
        signer=lambda value: openssl_rs256_sign(
            private_key_path,
            value,
        ),
    )

    token_response = send_request(
        build_installation_token_request(
            installation_id=installation_id,
            app_jwt=app_jwt,
            repository=target.repository,
        )
    )
    installation_token = installation_token_from_response(token_response)

    plan = build_github_checkout_plan(target)

    if workspace_parent is not None:
        workspace_parent = workspace_parent.expanduser().resolve()
        if not workspace_parent.is_dir():
            raise GitHubAppRuntimeError(
                "workspace_parent must be an existing directory"
            )
        workspace_dir = str(workspace_parent)
    else:
        workspace_dir = None

    with tempfile.TemporaryDirectory(
        prefix="cwb-app-",
        dir=workspace_dir,
    ) as temporary:
        checkout = checkout_github_repository(
            plan,
            installation_token=installation_token,
            destination=Path(temporary) / "repository",
        )

        check = build_github_app_check(checkout.root)
        check_response = send_request(
            build_check_run_request(
                repository=target.repository,
                head_sha=checkout.commit_sha,
                installation_token=installation_token,
                check=check,
            )
        )
        check_run_id, check_run_url = _check_run_metadata(check_response)

        return GitHubScanResult(
            repository=target.repository,
            commit_sha=checkout.commit_sha,
            conclusion=check.conclusion,
            check_run_id=check_run_id,
            check_run_url=check_run_url,
        )
