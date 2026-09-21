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
