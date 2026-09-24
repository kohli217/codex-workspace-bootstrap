from __future__ import annotations

from pathlib import Path
import re
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from codex_workspace_bootstrap.config import CONFIG_VERSION
from codex_workspace_bootstrap.preflight import PREFLIGHT_REPORT_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _documentation_paths() -> list[Path]:
    return sorted(
        path
        for directory in (
            ROOT,
            ROOT / "docs",
            ROOT / "deploy",
            ROOT / "examples",
            ROOT / "skills",
            ROOT / ".github",
        )
        for path in (directory.glob("*.md") if directory == ROOT else directory.rglob("*.md"))
    )


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
    for relative in ("README.md", "docs/GITHUB_ACTION.md", "docs/README.ja.md", "docs/STABILITY.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert f"codex-workspace-bootstrap@{expected_tag}" in text, (
            f"{relative} does not reference the current Action tag {expected_tag}"
        )

    action_pattern = re.compile(r"uses:\s*kohli217/codex-workspace-bootstrap@([^\s#]+)")
    for path in _documentation_paths():
        for ref in action_pattern.findall(path.read_text(encoding="utf-8")):
            assert ref == expected_tag, (
                f"{path.relative_to(ROOT)} documents stale Action ref {ref}; expected {expected_tag}"
            )


def test_documented_release_wheel_matches_package_version() -> None:
    version = _project_version()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    wheel_pattern = re.compile(
        r"https://github\.com/kohli217/codex-workspace-bootstrap/releases/download/"
        r"([^/\s]+)/codex_workspace_bootstrap-([^/\s]+)-py3-none-any\.whl"
    )
    wheels = wheel_pattern.findall(readme)
    assert wheels, "README.md must document the pinned release wheel"
    assert all(tag == f"v{version}" and wheel == version for tag, wheel in wheels), (
        f"README.md release wheel references {wheels!r} do not match v{version}"
    )


def test_documented_third_party_actions_are_sha_pinned() -> None:
    action_pattern = re.compile(
        r"uses:\s*((?:actions/|github/codeql-action/)[^@\s]+)@([^\s#]+)"
    )
    for path in _documentation_paths():
        text = path.read_text(encoding="utf-8")
        for action, ref in action_pattern.findall(text):
            assert re.fullmatch(r"[0-9a-f]{40}", ref), (
                f"{path.relative_to(ROOT)} documents mutable ref {action}@{ref}; "
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



def test_v1_stability_policy_keeps_public_compatibility_anchors() -> None:
    stability = (ROOT / "docs" / "STABILITY.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    japanese = (ROOT / "docs" / "README.ja.md").read_text(encoding="utf-8")
    integrations = (ROOT / "docs" / "INTEGRATIONS.md").read_text(encoding="utf-8")
    releasing = (ROOT / "docs" / "RELEASING.md").read_text(encoding="utf-8")

    assert "semantic versioning" in stability.lower()
    assert "schema_version" in stability
    assert ".cwb.json" in stability
    assert "Deprecation" in stability
    assert "security" in stability.lower()
    assert "docs/STABILITY.md" in readme
    assert "STABILITY.md" in japanese
    assert "STABILITY.md" in integrations
    assert "STABILITY.md" in releasing



def test_v1_release_metadata_guard() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(data["project"]["version"])
    major = int(version.split(".", 1)[0])

    if major < 1:
        return

    classifiers = set(data["project"].get("classifiers", []))
    assert "Development Status :: 3 - Alpha" not in classifiers
    assert "Development Status :: 5 - Production/Stable" in classifiers

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{version}]" in changelog, (
        f"CHANGELOG.md has no entry for v{version}"
    )

    stability = ROOT / "docs" / "STABILITY.md"
    schemas = ROOT / "docs" / "SCHEMAS.md"
    assert stability.is_file()
    assert schemas.is_file()

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/STABILITY.md" in readme

    assert PREFLIGHT_REPORT_SCHEMA_VERSION == 1
    assert CONFIG_VERSION == 1



def test_roadmap_has_no_literal_escaped_bullet_newlines() -> None:
    roadmap = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")

    assert "\\n-" not in roadmap
