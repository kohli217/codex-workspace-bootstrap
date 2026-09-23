# Releasing

Releases are created with GitHub Actions so the maintainer does not need to create local tags or upload build files manually.

## Before releasing

1. Ensure the default branch CI is green.
2. Ensure the version in `pyproject.toml` matches the intended release tag without the leading `v`.
3. Review `CHANGELOG.md`.
4. Confirm there are no unexpected files or credentials in the repository.

## One-click release

On GitHub:

1. Open **Actions**.
2. Select **Release**.
3. Click **Run workflow**.
4. Enter a semantic version tag such as `v0.1.0`.
5. Click **Run workflow**.

The workflow then:

- validates the tag format;
- verifies that the tag matches the package version;
- installs and tests the package;
- runs the repository self-audit in strict mode;
- builds and validates the wheel and source distribution;
- stores that exact wheel/source distribution pair as a short-lived workflow artifact for PyPI publication;
- creates GitHub artifact attestations and a Sigstore bundle;
- creates the GitHub tag and immutable release;
- attaches the distributions and Sigstore bundle to the release.

The release is created only after validation, tests, audit, build, distribution checks, and attestation succeed.

## Compatibility review for v1.x

Before a 1.x release, review [STABILITY.md](STABILITY.md) in addition to the changelog. Confirm that documented CLI behavior remains compatible, that any machine-readable breaking change increments its own schema/config version, and that newly added detector behavior is evidence-backed and covered by a deterministic regression fixture. Security fixes may intentionally tighten unsafe behavior instead of preserving insecure semantics.

The release-consistency suite also contains a dormant v1 guard. It activates automatically when the package major version becomes 1 or higher and rejects a release if PyPI metadata still says Alpha, if Production/Stable metadata is missing, if the exact version is absent from the changelog, if the stability/schema documents are missing, or if the v1 machine-contract versions are no longer explicit. This is intended to catch incomplete final-release preparation before the one-click Release workflow creates a tag.

## Permissions

The release job uses narrowly scoped GitHub permissions: `contents: write` to create the tag/release, plus `id-token: write`, `attestations: write`, and `artifact-metadata: write` for GitHub artifact attestations. It uses GitHub's ephemeral repository token and does not require a stored personal access token.


## PyPI Trusted Publishing

PyPI publishing uses GitHub Actions OpenID Connect (OIDC) Trusted Publishing. No long-lived PyPI API token is stored in GitHub.

Before the first publish:

1. Sign in to PyPI.
2. Create a pending Trusted Publisher for project name `codex-workspace-bootstrap`.
3. Provider: GitHub Actions.
4. Owner: `kohli217`.
5. Repository: `codex-workspace-bootstrap`.
6. Workflow filename: `pypi-publish.yml`.
7. Environment: `pypi`.

After a successful **Release** workflow, **Publish to PyPI** starts automatically. It downloads the exact wheel and source distribution produced by that triggering Release run and publishes those same bytes through OIDC. It does not select "the latest release" and does not rebuild during the automatic path.

A manual **Publish to PyPI** dispatch remains available only as a recovery path:

1. Open **Actions**.
2. Select **Publish to PyPI**.
3. Click **Run workflow**.
4. Enter an existing release tag such as `v0.6.1`.
5. Run the workflow.

The manual recovery path checks out that exact tag, verifies the package version, rebuilds and validates the distributions, and then publishes through OIDC.

Do not publish an unreleased working-tree state under an existing version number.
