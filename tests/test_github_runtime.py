from pathlib import Path
import io
import subprocess
from urllib.error import HTTPError

import pytest

from codex_workspace_bootstrap.integrations.github import GitHubCheckResult
from codex_workspace_bootstrap.integrations.github_checkout import (
    GitHubCheckoutResult,
)
from codex_workspace_bootstrap.integrations.github_delivery import (
    GitHubApiRequest,
)
from codex_workspace_bootstrap.integrations.github_runtime import (
    GitHubApiResponse,
    GitHubAppRuntimeError,
    execute_github_scan,
    installation_token_from_response,
    openssl_rs256_sign,
    send_github_api_request,
)
from codex_workspace_bootstrap.integrations.github_webhook import (
    GitHubWebhookTarget,
)
from codex_workspace_bootstrap.preflight import PolicyDecision


HEAD = "a" * 40


def test_openssl_signer_passes_key_path_not_key_contents(
    tmp_path: Path,
    monkeypatch,
) -> None:
    key = tmp_path / "app.pem"
    key.write_text("PRIVATE KEY MATERIAL", encoding="utf-8")
    seen: list[tuple[object, ...]] = []

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.shutil.which",
        lambda name: "/usr/bin/openssl",
    )

    def fake_run(
        args: tuple[str, ...],
        *,
        input: bytes,
        capture_output: bool,
        check: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[bytes]:
        seen.append(args)
        assert input == b"header.payload"
        return subprocess.CompletedProcess(args, 0, b"signature", b"")

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.subprocess.run",
        fake_run,
    )

    signature = openssl_rs256_sign(key, b"header.payload")

    assert signature == b"signature"
    assert len(seen) == 1
    assert seen[0][:4] == ("openssl", "dgst", "-sha256", "-sign")
    assert str(key.resolve()) in seen[0]
    assert "PRIVATE KEY MATERIAL" not in " ".join(str(item) for item in seen[0])


def test_installation_token_parser_does_not_assume_token_length() -> None:
    token = "ghs_1234567890_stateless_format_can_change_length"

    assert installation_token_from_response(
        GitHubApiResponse(
            status=201,
            body={"token": token, "expires_at": "2026-09-22T04:00:00Z"},
        )
    ) == token


def test_installation_token_parser_rejects_invalid_response() -> None:
    with pytest.raises(GitHubAppRuntimeError):
        installation_token_from_response(
            GitHubApiResponse(status=500, body={})
        )

    with pytest.raises(GitHubAppRuntimeError):
        installation_token_from_response(
            GitHubApiResponse(status=201, body={})
        )


def test_http_transport_serializes_json_and_headers(monkeypatch) -> None:
    request = GitHubApiRequest(
        method="POST",
        url="https://api.github.com/example",
        headers={
            "Authorization": "Bearer token",
            "User-Agent": "codex-workspace-bootstrap",
        },
        json_body={"hello": "world"},
    )
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, size: int) -> bytes:
            captured["read_size"] = size
            return b'{"id":123}'

    def fake_urlopen(http_request, *, timeout: int):
        captured["request"] = http_request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.urlopen",
        fake_urlopen,
    )

    response = send_github_api_request(request)

    assert response == GitHubApiResponse(status=201, body={"id": 123})
    http_request = captured["request"]
    assert http_request.get_method() == "POST"
    assert http_request.get_header("Authorization") == "Bearer token"
    assert http_request.get_header("User-agent") == "codex-workspace-bootstrap"
    assert http_request.get_header("Content-type") == "application/json"
    assert http_request.data == b'{"hello":"world"}'
    assert captured["timeout"] == 20


def test_http_transport_redacts_github_error_body(monkeypatch) -> None:
    def fail_urlopen(http_request, *, timeout: int):
        raise HTTPError(
            http_request.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"message":"token ghs_should_not_leak"}'),
        )

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.urlopen",
        fail_urlopen,
    )

    with pytest.raises(GitHubAppRuntimeError) as exc_info:
        send_github_api_request(
            GitHubApiRequest(
                method="POST",
                url="https://api.github.com/example",
                headers={"Authorization": "Bearer secret"},
            )
        )

    assert "401" in str(exc_info.value)
    assert "ghs_should_not_leak" not in str(exc_info.value)
    assert "secret" not in str(exc_info.value)


def test_execute_scan_scopes_token_and_posts_check_for_inspected_sha(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = GitHubWebhookTarget(
        event="push",
        repository="octo/demo",
        head_sha=HEAD,
        installation_id=1234,
        ref="refs/heads/main",
    )
    private_key = tmp_path / "app.pem"
    private_key.write_text("key", encoding="utf-8")
    requests: list[GitHubApiRequest] = []

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.openssl_rs256_sign",
        lambda path, value: b"signature",
    )

    def fake_checkout(plan, *, installation_token: str, destination: Path):
        assert installation_token == "ghs_runtime_token"
        destination.mkdir(parents=True)
        return GitHubCheckoutResult(
            root=destination,
            commit_sha=HEAD,
            fetched_ref=HEAD,
        )

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.checkout_github_repository",
        fake_checkout,
    )

    fake_check = GitHubCheckResult(
        name="CWB Preflight",
        conclusion="success",
        title="CWB preflight: READY",
        summary="# report",
        policy=PolicyDecision(True, ()),
    )
    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.build_github_app_check",
        lambda root: fake_check,
    )

    def fake_send(request: GitHubApiRequest) -> GitHubApiResponse:
        requests.append(request)
        if request.url.endswith("/access_tokens"):
            return GitHubApiResponse(
                status=201,
                body={"token": "ghs_runtime_token"},
            )
        return GitHubApiResponse(
            status=201,
            body={
                "id": 987,
                "html_url": "https://github.com/octo/demo/runs/987",
            },
        )

    result = execute_github_scan(
        target,
        client_id="Iv23liExample",
        private_key_path=private_key,
        workspace_parent=tmp_path,
        now=1_800_000_000,
        send_request=fake_send,
    )

    assert result.repository == "octo/demo"
    assert result.commit_sha == HEAD
    assert result.conclusion == "success"
    assert result.check_run_id == 987
    assert result.check_run_url == "https://github.com/octo/demo/runs/987"

    assert len(requests) == 2
    token_request = requests[0]
    assert token_request.json_body == {
        "repositories": ["demo"],
        "permissions": {
            "checks": "write",
            "contents": "read",
        },
    }

    check_request = requests[1]
    assert check_request.json_body is not None
    assert check_request.json_body["head_sha"] == HEAD
    assert check_request.headers["Authorization"] == "Bearer ghs_runtime_token"


def test_execute_scan_requires_installation_id(tmp_path: Path) -> None:
    with pytest.raises(GitHubAppRuntimeError, match="installation_id"):
        execute_github_scan(
            GitHubWebhookTarget(
                event="push",
                repository="octo/demo",
                head_sha=HEAD,
                installation_id=None,
            ),
            client_id="Iv23liExample",
            private_key_path=tmp_path / "missing.pem",
        )



def test_execute_scan_reuses_completed_check_for_same_delivery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = GitHubWebhookTarget(
        event="push",
        repository="octo/demo",
        head_sha=HEAD,
        installation_id=1234,
        ref="refs/heads/main",
    )
    private_key = tmp_path / "app.pem"
    private_key.write_text("key", encoding="utf-8")
    requests: list[GitHubApiRequest] = []

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.openssl_rs256_sign",
        lambda path, value: b"signature",
    )

    def fake_checkout(plan, *, installation_token: str, destination: Path):
        destination.mkdir(parents=True)
        return GitHubCheckoutResult(
            root=destination,
            commit_sha=HEAD,
            fetched_ref=HEAD,
        )

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.checkout_github_repository",
        fake_checkout,
    )
    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.build_github_app_check",
        lambda root: (_ for _ in ()).throw(
            AssertionError("deduplicated delivery must not rerun preflight")
        ),
    )

    def fake_send(request: GitHubApiRequest) -> GitHubApiResponse:
        requests.append(request)
        if request.url.endswith("/access_tokens"):
            return GitHubApiResponse(
                status=201,
                body={"token": "ghs_runtime_token"},
            )
        if "/check-runs?" in request.url:
            return GitHubApiResponse(
                status=200,
                body={
                    "check_runs": [
                        {
                            "id": 987,
                            "external_id": "delivery-123",
                            "html_url": "https://github.com/octo/demo/runs/987",
                            "conclusion": "success",
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    result = execute_github_scan(
        target,
        client_id="Iv23liExample",
        private_key_path=private_key,
        workspace_parent=tmp_path,
        now=1_800_000_000,
        external_id="delivery-123",
        send_request=fake_send,
    )

    assert result.repository == "octo/demo"
    assert result.commit_sha == HEAD
    assert result.conclusion == "success"
    assert result.check_run_id == 987
    assert result.check_run_url == "https://github.com/octo/demo/runs/987"
    assert result.deduplicated is True
    assert [request.method for request in requests] == ["POST", "GET"]


def test_execute_scan_creates_check_when_delivery_is_new(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = GitHubWebhookTarget(
        event="push",
        repository="octo/demo",
        head_sha=HEAD,
        installation_id=1234,
        ref="refs/heads/main",
    )
    private_key = tmp_path / "app.pem"
    private_key.write_text("key", encoding="utf-8")
    requests: list[GitHubApiRequest] = []

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.openssl_rs256_sign",
        lambda path, value: b"signature",
    )

    def fake_checkout(plan, *, installation_token: str, destination: Path):
        destination.mkdir(parents=True)
        return GitHubCheckoutResult(
            root=destination,
            commit_sha=HEAD,
            fetched_ref=HEAD,
        )

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.checkout_github_repository",
        fake_checkout,
    )

    fake_check = GitHubCheckResult(
        name="CWB Preflight",
        conclusion="success",
        title="CWB preflight: READY",
        summary="# report",
        policy=PolicyDecision(True, ()),
    )
    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.build_github_app_check",
        lambda root: fake_check,
    )

    def fake_send(request: GitHubApiRequest) -> GitHubApiResponse:
        requests.append(request)
        if request.url.endswith("/access_tokens"):
            return GitHubApiResponse(
                status=201,
                body={"token": "ghs_runtime_token"},
            )
        if "/check-runs?" in request.url:
            return GitHubApiResponse(
                status=200,
                body={"check_runs": []},
            )
        if request.url.endswith("/check-runs"):
            return GitHubApiResponse(
                status=201,
                body={
                    "id": 988,
                    "html_url": "https://github.com/octo/demo/runs/988",
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    result = execute_github_scan(
        target,
        client_id="Iv23liExample",
        private_key_path=private_key,
        workspace_parent=tmp_path,
        now=1_800_000_000,
        external_id="delivery-new",
        send_request=fake_send,
    )

    assert result.deduplicated is False
    assert result.check_run_id == 988
    assert [request.method for request in requests] == ["POST", "GET", "POST"]
    assert requests[-1].json_body is not None
    assert requests[-1].json_body["external_id"] == "delivery-new"


def test_incomplete_matching_check_does_not_suppress_retry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = GitHubWebhookTarget(
        event="push",
        repository="octo/demo",
        head_sha=HEAD,
        installation_id=1234,
    )
    private_key = tmp_path / "app.pem"
    private_key.write_text("key", encoding="utf-8")

    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.openssl_rs256_sign",
        lambda path, value: b"signature",
    )
    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.checkout_github_repository",
        lambda plan, *, installation_token, destination: GitHubCheckoutResult(
            root=tmp_path,
            commit_sha=HEAD,
            fetched_ref=HEAD,
        ),
    )
    fake_check = GitHubCheckResult(
        name="CWB Preflight",
        conclusion="success",
        title="CWB preflight: READY",
        summary="# report",
        policy=PolicyDecision(True, ()),
    )
    monkeypatch.setattr(
        "codex_workspace_bootstrap.integrations.github_runtime.build_github_app_check",
        lambda root: fake_check,
    )

    call_count = 0

    def fake_send(request: GitHubApiRequest) -> GitHubApiResponse:
        nonlocal call_count
        call_count += 1
        if request.url.endswith("/access_tokens"):
            return GitHubApiResponse(status=201, body={"token": "token"})
        if "/check-runs?" in request.url:
            return GitHubApiResponse(
                status=200,
                body={
                    "check_runs": [
                        {
                            "id": 1,
                            "external_id": "delivery-123",
                            "conclusion": None,
                        }
                    ]
                },
            )
        return GitHubApiResponse(status=201, body={"id": 2})

    result = execute_github_scan(
        target,
        client_id="Iv23liExample",
        private_key_path=private_key,
        now=1_800_000_000,
        external_id="delivery-123",
        send_request=fake_send,
    )

    assert result.deduplicated is False
    assert result.check_run_id == 2
    assert call_count == 3
