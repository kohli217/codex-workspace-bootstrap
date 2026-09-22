from __future__ import annotations

from dataclasses import dataclass
import hmac
import html
import json
import secrets
from urllib.parse import quote, urlparse

from .github_app import required_github_app_registration


GITHUB_PERSONAL_APP_MANIFEST_URL = "https://github.com/settings/apps/new"
GITHUB_MANIFEST_CONVERSION_URL = (
    "https://api.github.com/app-manifests/{code}/conversions"
)


class GitHubManifestError(ValueError):
    """Raised when GitHub App Manifest flow input is unsafe or incomplete."""


@dataclass(frozen=True)
class GitHubManifestRegistration:
    action_url: str
    manifest_json: str
    state: str


@dataclass(frozen=True, repr=False)
class GitHubManifestCredentials:
    app_id: int
    client_id: str
    private_key_pem: str
    webhook_secret: str
    slug: str | None = None

    def public_metadata(self) -> dict[str, object]:
        """Return fields that are safe to log or display."""

        return {
            "app_id": self.app_id,
            "client_id": self.client_id,
            "slug": self.slug,
        }


def _https_base_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise GitHubManifestError(
            "base_url must be an absolute HTTPS URL without credentials, query, or fragment"
        )
    return value


def build_github_app_manifest(
    *,
    base_url: str,
    name: str = "CWB Preflight Dev",
    public: bool = False,
) -> dict[str, object]:
    """Build the GitHub App Manifest from CWB's code-level registration contract."""

    base = _https_base_url(base_url)
    if not name.strip():
        raise GitHubManifestError("GitHub App name must not be empty")

    registration = required_github_app_registration()
    return {
        "name": name.strip(),
        "url": "https://github.com/kohli217/codex-workspace-bootstrap",
        "description": (
            "Repository preflight checks for AI coding readiness and instruction integrity."
        ),
        "hook_attributes": {
            "url": f"{base}/webhooks/github",
            "active": True,
        },
        "redirect_url": f"{base}/setup/github/callback",
        "public": public,
        "default_permissions": registration.repository_permissions,
        "default_events": list(registration.webhook_events),
        "request_oauth_on_install": False,
        "setup_on_update": False,
    }


def build_manifest_registration(
    *,
    base_url: str,
    name: str = "CWB Preflight Dev",
    public: bool = False,
    state: str | None = None,
) -> GitHubManifestRegistration:
    """Build the form target + manifest payload for GitHub's manifest handshake."""

    state_value = state or secrets.token_urlsafe(32)
    if not state_value.strip():
        raise GitHubManifestError("manifest state must not be empty")

    manifest = build_github_app_manifest(
        base_url=base_url,
        name=name,
        public=public,
    )
    return GitHubManifestRegistration(
        action_url=(
            GITHUB_PERSONAL_APP_MANIFEST_URL
            + "?state="
            + quote(state_value, safe="")
        ),
        manifest_json=json.dumps(
            manifest,
            separators=(",", ":"),
            sort_keys=True,
        ),
        state=state_value,
    )


def render_manifest_registration_form(
    registration: GitHubManifestRegistration,
    *,
    button_label: str = "Register CWB GitHub App",
) -> str:
    """Render a minimal POST form compatible with GitHub's App Manifest flow."""

    if not button_label.strip():
        raise GitHubManifestError("button label must not be empty")

    return (
        '<form method="post" action="'
        + html.escape(registration.action_url, quote=True)
        + '">'
        + '<input type="hidden" name="manifest" value="'
        + html.escape(registration.manifest_json, quote=True)
        + '">'
        + '<button type="submit">'
        + html.escape(button_label)
        + "</button></form>"
    )


def verify_manifest_callback_state(
    *,
    expected_state: str,
    received_state: str | None,
) -> None:
    """Reject manifest callbacks that do not match the initiating CSRF state."""

    if not expected_state or received_state is None:
        raise GitHubManifestError("manifest callback state is missing")
    if not hmac.compare_digest(expected_state, received_state):
        raise GitHubManifestError("manifest callback state does not match")


def manifest_conversion_url(code: str) -> str:
    """Return the one-hour manifest conversion endpoint for a temporary code."""

    if not code.strip():
        raise GitHubManifestError("manifest conversion code must not be empty")
    return GITHUB_MANIFEST_CONVERSION_URL.format(
        code=quote(code, safe=""),
    )


def parse_manifest_conversion_response(
    payload: dict[str, object],
) -> GitHubManifestCredentials:
    """Extract generated App credentials without exposing them via repr/log metadata."""

    app_id = payload.get("id")
    client_id = payload.get("client_id")
    private_key = payload.get("pem")
    webhook_secret = payload.get("webhook_secret")
    slug = payload.get("slug")

    if isinstance(app_id, bool) or not isinstance(app_id, int) or app_id <= 0:
        raise GitHubManifestError("manifest conversion response is missing app id")
    if not isinstance(client_id, str) or not client_id.strip():
        raise GitHubManifestError("manifest conversion response is missing client_id")
    if not isinstance(private_key, str) or "PRIVATE KEY" not in private_key:
        raise GitHubManifestError("manifest conversion response is missing private key")
    if not isinstance(webhook_secret, str) or not webhook_secret.strip():
        raise GitHubManifestError("manifest conversion response is missing webhook secret")
    if slug is not None and (not isinstance(slug, str) or not slug.strip()):
        raise GitHubManifestError("manifest conversion response has invalid slug")

    return GitHubManifestCredentials(
        app_id=app_id,
        client_id=client_id,
        private_key_pem=private_key,
        webhook_secret=webhook_secret,
        slug=slug,
    )
