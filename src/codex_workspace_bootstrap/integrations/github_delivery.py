from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import base64
import json
from urllib.parse import quote, urlencode

from .github import GitHubCheckResult


GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
GITHUB_ACCEPT = "application/vnd.github+json"
GITHUB_USER_AGENT = "codex-workspace-bootstrap"


class GitHubDeliveryContractError(ValueError):
    """Raised when GitHub delivery inputs cannot be represented safely."""


@dataclass(frozen=True)
class GitHubApiRequest:
    method: str
    url: str
    headers: dict[str, str]
    json_body: dict[str, object] | None = None


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _compact_json(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def build_github_app_jwt_signing_input(
    *,
    client_id: str,
    now: int,
) -> bytes:
    """Build the RS256 JWT signing input required for GitHub App authentication."""

    if not client_id.strip():
        raise GitHubDeliveryContractError("GitHub App client_id must not be empty")
    if now <= 0:
        raise GitHubDeliveryContractError("JWT timestamp must be a positive Unix time")

    header = {
        "alg": "RS256",
        "typ": "JWT",
    }
    payload = {
        "exp": now + 540,
        "iat": now - 60,
        "iss": client_id,
    }
    return (
        _base64url(_compact_json(header))
        + "."
        + _base64url(_compact_json(payload))
    ).encode("ascii")


def assemble_github_app_jwt(
    signing_input: bytes,
    signature: bytes,
) -> str:
    """Combine a JWT signing input with an externally produced RS256 signature."""

    if not signing_input or signing_input.count(b".") != 1:
        raise GitHubDeliveryContractError("invalid JWT signing input")
    if not signature:
        raise GitHubDeliveryContractError("JWT signature must not be empty")

    return signing_input.decode("ascii") + "." + _base64url(signature)


def build_github_app_jwt(
    *,
    client_id: str,
    now: int,
    signer: Callable[[bytes], bytes],
) -> str:
    """Create a GitHub App JWT using an injected RS256 signer."""

    signing_input = build_github_app_jwt_signing_input(
        client_id=client_id,
        now=now,
    )
    signature = signer(signing_input)
    return assemble_github_app_jwt(signing_input, signature)


def _headers(token: str) -> dict[str, str]:
    if not token.strip():
        raise GitHubDeliveryContractError("GitHub API token must not be empty")
    return {
        "Accept": GITHUB_ACCEPT,
        "Authorization": f"Bearer {token}",
        "User-Agent": GITHUB_USER_AGENT,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


def build_installation_token_request(
    *,
    installation_id: int,
    app_jwt: str,
    repository: str | None = None,
) -> GitHubApiRequest:
    """Build GitHub's installation-access-token request."""

    if (
        isinstance(installation_id, bool)
        or not isinstance(installation_id, int)
        or installation_id <= 0
    ):
        raise GitHubDeliveryContractError("installation_id must be a positive integer")

    json_body: dict[str, object] | None = None
    if repository is not None:
        _, repo = _repository_parts(repository)
        json_body = {
            "repositories": [repo],
            "permissions": {
                "checks": "write",
                "contents": "read",
            },
        }

    return GitHubApiRequest(
        method="POST",
        url=(
            f"{GITHUB_API_BASE_URL}/app/installations/"
            f"{installation_id}/access_tokens"
        ),
        headers=_headers(app_jwt),
        json_body=json_body,
    )


def _repository_parts(repository: str) -> tuple[str, str]:
    parts = repository.split("/")
    if len(parts) != 2 or not all(part.strip() for part in parts):
        raise GitHubDeliveryContractError(
            "repository must use GitHub owner/name form"
        )
    return parts[0], parts[1]


def build_check_run_request(
    *,
    repository: str,
    head_sha: str,
    installation_token: str,
    check: GitHubCheckResult,
    external_id: str | None = None,
) -> GitHubApiRequest:
    """Build a completed GitHub Check Run request for an inspected commit."""

    owner, repo = _repository_parts(repository)
    if not head_sha.strip():
        raise GitHubDeliveryContractError("head_sha must not be empty")

    body = dict(check.to_check_run_fields())
    body["head_sha"] = head_sha
    if external_id is not None:
        if not external_id.strip():
            raise GitHubDeliveryContractError("external_id must not be empty")
        body["external_id"] = external_id

    return GitHubApiRequest(
        method="POST",
        url=(
            f"{GITHUB_API_BASE_URL}/repos/"
            f"{quote(owner, safe='')}/{quote(repo, safe='')}/check-runs"
        ),
        headers=_headers(installation_token),
        json_body=body,
    )



def build_list_check_runs_request(
    *,
    repository: str,
    ref: str,
    installation_token: str,
    check_name: str = "CWB Preflight",
) -> GitHubApiRequest:
    """Build a request that lists CWB Check Runs for one exact Git ref."""

    owner, repo = _repository_parts(repository)
    if not ref.strip():
        raise GitHubDeliveryContractError("ref must not be empty")
    if not check_name.strip():
        raise GitHubDeliveryContractError("check_name must not be empty")

    query = urlencode(
        {
            "check_name": check_name,
            "filter": "all",
            "per_page": 100,
        }
    )
    return GitHubApiRequest(
        method="GET",
        url=(
            f"{GITHUB_API_BASE_URL}/repos/"
            f"{quote(owner, safe='')}/{quote(repo, safe='')}/commits/"
            f"{quote(ref, safe='')}/check-runs?{query}"
        ),
        headers=_headers(installation_token),
    )
