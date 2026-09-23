# Privacy Policy

_Last updated: 2026-09-23_

This privacy policy describes how the community-maintained **CWB Preflight** GitHub App and the `codex-workspace-bootstrap` project handle information.

## Scope

This policy covers the public CWB Preflight GitHub App operated from this repository and its zero-cost Cloudflare deployment. It does not cover GitHub, Cloudflare, or other third-party services, which are governed by their own policies.

The hosted CWB Preflight service is intentionally limited to **public repositories**. Private-repository webhook events are rejected before they are queued for scanning.

## Information processed for repository checks

When GitHub sends a supported push or pull-request webhook, the service processes the minimum metadata needed to inspect the selected public repository revision and publish a Check Run. This can include:

- repository full name;
- repository owner account ID;
- GitHub App installation ID;
- commit SHA and Git ref;
- pull-request number and action when applicable;
- GitHub webhook delivery ID.

The scan worker checks out the exact public repository revision using a short-lived, repository-scoped GitHub App installation token. CWB reads repository files required by its deterministic preflight checks, such as repository instructions and project metadata. It does not send repository contents to a remote AI model.

## Private repositories

The free hosted deployment does not support private repositories. Events for private repositories are rejected at the Cloudflare gateway before they enter the public GitHub Actions worker.

## Marketplace onboarding

For GitHub Marketplace onboarding, CWB Preflight uses GitHub's user authorization flow only to verify the identity of the person completing installation.

The Setup URL binds GitHub's `installation_id` into a signed, short-lived OAuth state. After OAuth, CWB checks that the authenticated GitHub user can access that exact installation before setup succeeds. The resulting GitHub user access token:

- is used only to call GitHub's authenticated user endpoint;
- is not written to Workers KV, GitHub Actions artifacts, repository files, or application logs;
- is immediately submitted to GitHub's token-revocation endpoint after successful identity verification.

If the revocation request fails, CWB still does not persist the token; GitHub controls its remaining lifetime.

## Marketplace plan state

GitHub Marketplace sends plan lifecycle events to a separately signed webhook. CWB stores only the numeric GitHub account ID and minimal plan state needed to avoid processing scans for an explicitly cancelled Marketplace account.

For an active Marketplace plan, the stored record contains only:

- numeric account ID as the KV key;
- active/cancelled state;
- Marketplace action;
- numeric plan ID when supplied by GitHub;
- effective date when supplied by GitHub;
- last-updated timestamp.

CWB does not store the customer's GitHub login in Marketplace state.

When GitHub reports a Marketplace cancellation, CWB first records the account as inactive, then requests removal of the matching CWB Preflight GitHub App installation. The minimal cancellation record expires from Workers KV within 30 days. Direct public GitHub App installations that have no Marketplace record continue to use the existing free public-App path.

## Credentials and security data

CWB stores operator credentials required to run the GitHub App, including the App private key and webhook secret, in the deployment's secret storage. These are service credentials, not customer-provided repository data.

GitHub installation tokens are short-lived and restricted to the single repository being inspected. They are not stored for later reuse.

## Logs and third-party infrastructure

The hosted service uses GitHub and Cloudflare infrastructure. Operational logs may contain non-secret metadata such as request status, workflow identifiers, or error categories. CWB is designed not to log GitHub App private keys, webhook secrets, installation tokens, Marketplace user access tokens, or repository file contents.

GitHub Actions may retain normal workflow metadata according to GitHub's retention rules. Cloudflare may process request and platform metadata according to Cloudflare's service terms and privacy practices.

## Data sharing and sale

CWB does not sell personal data. The project does not provide repository contents or Marketplace identity data to advertisers.

Data is processed only through the infrastructure needed to provide the service, primarily GitHub and Cloudflare.

## Data deletion

CWB does not maintain a separate hosted customer profile database.

- Marketplace cancellation records expire within 30 days.
- Marketplace OAuth user access tokens are not retained.
- A Marketplace cancellation requests removal of the matching GitHub App installation after the inactive state is persisted.
- Uninstalling the GitHub App stops future repository webhook processing for that installation.

For a privacy or deletion question, open a support request without including secrets or private repository contents.

## Children

CWB Preflight is developer tooling and is not directed at children.

## Changes to this policy

Material changes will be published in this repository with normal Git history.

## Contact and support

For support or privacy questions, use [SUPPORT.md](SUPPORT.md).

For security-sensitive reports, follow [SECURITY.md](SECURITY.md) and use GitHub private vulnerability reporting rather than a public issue.
