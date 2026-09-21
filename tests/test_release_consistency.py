from __future__ import annotations

from pathlib import Path
import re
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]


def _project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_release_version_references_stay_in_sync() -> None:
    version = _project_version()

    init_text = (ROOT / "src" / "codex_workspace_bootstrap" / "__init__.py").read_text(encoding="utf-8")
    init_match = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
    assert init_match, "__version__ is missing"
    assert init_match.group(1) == version

    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    citation_match = re.search(r"^version:\s*([^\s]+)\s*$", citation, re.MULTILINE)
    assert citation_match, "CITATION.cff version is missing"
    assert citation_match.group(1) == version

    expected_tag = f"v{version}"
    for relative in ("README.md", "docs/GITHUB_ACTION.md", "docs/README.ja.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert f"codex-workspace-bootstrap@{expected_tag}" in text, (
            f"{relative} does not reference the current Action tag {expected_tag}"
        )


def test_documented_third_party_actions_are_sha_pinned() -> None:
    action_pattern = re.compile(
        r"uses:\s*((?:actions/|github/codeql-action/)[^@\s]+)@([^\s#]+)"
    )
    for relative in ("README.md", "docs/GITHUB_ACTION.md", "docs/README.ja.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for action, ref in action_pattern.findall(text):
            assert re.fullmatch(r"[0-9a-f]{40}", ref), (
                f"{relative} documents mutable ref {action}@{ref}; "
                "pin third-party actions to a full commit SHA"
            )


def test_pypi_auto_publish_uses_triggering_release_artifact() -> None:
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    publish = (ROOT / ".github" / "workflows" / "pypi-publish.yml").read_text(encoding="utf-8")

    assert "name: python-package-distributions" in release
    assert "dist/*.whl" in release
    assert "dist/*.tar.gz" in release
    assert "python -m twine check dist/*" in release

    assert "github.event.workflow_run.id" in publish
    assert "github-token: ${{ github.token }}" in publish
    assert "Download exact distributions from triggering Release run" in publish
    assert "gh release view" not in publish


def test_release_documentation_matches_attestation_permissions() -> None:
    docs = (ROOT / "docs" / "RELEASING.md").read_text(encoding="utf-8")

    for permission in (
        "contents: write",
        "id-token: write",
        "attestations: write",
        "artifact-metadata: write",
    ):
        assert f"`{permission}`" in docs


def test_powershell_installer_default_matches_package_version() -> None:
    version = _project_version()
    installer = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")

    assert f'[string]$Version = "{version}"' in installer
    assert "releases/download/v$Version/codex_workspace_bootstrap-$Version-py3-none-any.whl" in installer
    assert 'Write-Host "  cwb preflight ."' in installer
