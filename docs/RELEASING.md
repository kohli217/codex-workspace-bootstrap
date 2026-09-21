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
- builds the wheel and source distribution;
- creates the GitHub tag and release;
- attaches the distributions to the release.

The release is created only after the validation, test, audit, and build steps succeed.

## Permissions

The workflow requests only `contents: write`, which is required to create the tag and GitHub release. It uses GitHub's ephemeral repository token and does not require a stored personal access token.


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

Then on GitHub:

1. Open **Actions**.
2. Select **Publish to PyPI**.
3. Click **Run workflow**.
4. Enter an existing release tag such as `v0.3.0`.
5. Run the workflow.

The workflow checks out the exact release tag, verifies the package version, builds wheel and source distributions, validates them with Twine, and publishes through OIDC.

Do not publish an unreleased working-tree state under an existing version number.
