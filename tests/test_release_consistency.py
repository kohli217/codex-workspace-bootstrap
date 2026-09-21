from __future__ import annotations

from pathlib import Path
import re
import tomllib

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
