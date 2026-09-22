import base64
import json

import pytest

from codex_workspace_bootstrap.integrations.github import build_github_check
from codex_workspace_bootstrap.integrations.github_delivery import (
    GITHUB_ACCEPT,
    GITHUB_API_VERSION,
    GitHubDeliveryContractError,
    assemble_github_app_jwt,
    build_check_run_request,
    build_github_app_jwt,
    build_github_app_jwt_signing_input,
    build_installation_token_request,
)
from codex_workspace_bootstrap.preflight import PREFLIGHT_REPORT_SCHEMA_VERSION


def _decode(segment: bytes) -> dict[str, object]:
    padding = b"=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(segment + padding))


def _report() -> dict[str, object]:
    return {
        "schema_version": PREFLIGHT_REPORT_SCHEMA_VERSION,
        "repository": "/repo",
        "local_toolchain_checked": False,
        "state": "READY",
        "project_signals": [],
        "instruction_signals": [],
        "instruction_findings": [],
        "instruction_summary": {
            "findings": 0,
            "drift": 0,
            "invalid_commands": 0,
            "metadata": 0,
        },
        "summary": {
            "passed": 1,
            "warnings": 0,
            "blocking": 0,
        },
        "next_actions": [],
        "checks": [],
    }


def test_jwt_signing_input_matches_github_claim_contract() -> None:
    now = 1_800_000_000

    signing_input = build_github_app_jwt_signing_input(
        client_id="Iv23liExample",
        now=now,
    )

    header_segment, payload_segment = signing_input.split(b".")
    assert _decode(header_segment) == {
        "alg": "RS256",
        "typ": "JWT",
    }
    assert _decode(payload_segment) == {
        "exp": now + 540,
        "iat": now - 60,
        "iss": "Iv23liExample",
    }


def test_build_github_app_jwt_uses_injected_signer() -> None:
    seen: list[bytes] = []

    def signer(signing_input: bytes) -> bytes:
        seen.append(signing_input)
        return b"rsa-signature"

    token = build_github_app_jwt(
        client_id="Iv23liExample",
        now=1_800_000_000,
        signer=signer,
    )

    assert len(seen) == 1
    assert token.startswith(seen[0].decode("ascii") + ".")
    assert token.endswith("cnNhLXNpZ25hdHVyZQ")


def test_assemble_jwt_rejects_invalid_inputs() -> None:
    with pytest.raises(GitHubDeliveryContractError):
        assemble_github_app_jwt(b"not-a-jwt-input", b"signature")

    with pytest.raises(GitHubDeliveryContractError):
        assemble_github_app_jwt(b"header.payload", b"")


def test_installation_token_request_uses_current_github_headers() -> None:
    request = build_installation_token_request(
        installation_id=1234,
        app_jwt="app.jwt.token",
    )

    assert request.method == "POST"
    assert request.url == (
        "https://api.github.com/app/installations/1234/access_tokens"
    )
    assert request.headers == {
        "Accept": GITHUB_ACCEPT,
        "Authorization": "Bearer app.jwt.token",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    assert GITHUB_API_VERSION == "2026-03-10"
    assert request.json_body is None


def test_check_run_request_combines_adapter_fields_and_head_sha() -> None:
    check = build_github_check(_report())

    request = build_check_run_request(
        repository="octo/demo",
        head_sha="abc123",
        installation_token="ghs_example",
        check=check,
    )

    assert request.method == "POST"
    assert request.url == "https://api.github.com/repos/octo/demo/check-runs"
    assert request.headers["Authorization"] == "Bearer ghs_example"
    assert request.headers["X-GitHub-Api-Version"] == "2026-03-10"
    assert request.json_body is not None
    assert request.json_body["head_sha"] == "abc123"
    assert request.json_body["name"] == "CWB Preflight"
    assert request.json_body["status"] == "completed"
    assert request.json_body["conclusion"] == "success"


@pytest.mark.parametrize(
    ("repository", "head_sha"),
    [
        ("missing-slash", "abc123"),
        ("/repo", "abc123"),
        ("owner/", "abc123"),
        ("owner/repo/extra", "abc123"),
        ("owner/repo", ""),
    ],
)
def test_check_run_request_rejects_invalid_target(
    repository: str,
    head_sha: str,
) -> None:
    check = build_github_check(_report())

    with pytest.raises(GitHubDeliveryContractError):
        build_check_run_request(
            repository=repository,
            head_sha=head_sha,
            installation_token="token",
            check=check,
        )


@pytest.mark.parametrize("installation_id", [0, -1, True, "123"])
def test_installation_token_request_rejects_invalid_installation_id(
    installation_id: object,
) -> None:
    with pytest.raises(GitHubDeliveryContractError):
        build_installation_token_request(
            installation_id=installation_id,
            app_jwt="app.jwt.token",
        )
