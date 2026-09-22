# Completely free GitHub App deployment

This is the preferred zero-cost development deployment for CWB.

**This free path is intentionally limited to public repositories.** Private-repository webhook events are rejected by the Cloudflare gateway before they are queued, so private repository names, commit SHAs, or code are never handed to a public GitHub Actions run.

It uses only services that have a usable free tier without enabling a paid Google Cloud project:

```text
GitHub App webhook
        ↓
Cloudflare Worker (Free)
        ↓
Cloudflare Queue (Free)
        ↓
workflow_dispatch
        ↓
GitHub Actions in this public repository
        ↓
OIDC-authenticated token request back to Cloudflare
        ↓
single-repository GitHub App installation token
        ↓
secure checkout + CWB repository-only preflight
        ↓
GitHub Check Run
```

## Cost boundary

The deployment script does not enable a paid Cloudflare Workers plan.

On the current Workers Free plan:

- Workers include 100,000 requests per day.
- Queues include 10,000 operations per day and 24-hour message retention.
- Workers KV includes 100,000 reads and 1,000 writes per day plus 1 GB of stored data on the Free plan.
- standard GitHub-hosted Actions runners are free for public repositories.

When a Cloudflare Free-plan limit is exhausted, further free-plan operations fail until the quota resets rather than this deployment automatically upgrading the account. Do not opt into Workers Paid if the goal is a strict zero-cost deployment.

## Why the Queue remains

GitHub does not automatically retry failed webhook deliveries. The public Worker therefore acknowledges GitHub only after the verified event has been accepted into Cloudflare Queue.

The Queue consumer triggers the public CWB GitHub Actions workflow. If GitHub's workflow-dispatch API is temporarily unavailable, the Queue message is retried instead of silently disappearing.

## Credential boundary

The GitHub App Manifest callback stores the generated App client ID, private key, and webhook secret in Workers KV. Cloudflare encrypts all KV values at rest with AES-256 and protects transport with TLS.

The GitHub Actions runner never receives the App private key or webhook secret.

When a scan starts:

1. GitHub Actions requests an OIDC token using `id-token: write`.
2. Cloudflare verifies the token signature against GitHub's OIDC keys.
3. Cloudflare requires:
   - repository `kohli217/codex-workspace-bootstrap`;
   - branch `refs/heads/main`;
   - event `workflow_dispatch`;
   - exact workflow `.github/workflows/github-app-worker.yml`.
4. The queued webhook target carries an HMAC broker grant derived from the App webhook secret. The grant binds the delivery ID, event, repository, installation ID, exact commit SHA, pull-request metadata, merge SHA, and ref. A manually altered workflow input therefore cannot mint a token for a different scan target.
5. Cloudflare creates an installation token restricted to only the event repository and only `contents:read` + `checks:write`.
6. The Actions runner uses that short-lived token for checkout and Check Run publication.

The only long-lived GitHub credential supplied manually is a fine-grained personal access token scoped to **only** `kohli217/codex-workspace-bootstrap` with **Actions: Read and write** and **Variables: Read and write**. The deployment script uses Variables write once to pin the trusted `CWB_TOKEN_ENDPOINT`; the deployed Worker uses the token only for `workflow_dispatch`.

## Windows deployment

Prerequisites:

- a free Cloudflare account;
- Node.js 18 or newer;
- a fine-grained GitHub personal access token limited to this repository with **Actions: Read and write** and **Variables: Read and write**.

From PowerShell:

```powershell
git clone https://github.com/kohli217/codex-workspace-bootstrap.git
cd codex-workspace-bootstrap
powershell -ExecutionPolicy Bypass -File .\deploy\cloudflare\deploy.ps1
```

The script:

1. checks Node/npm;
2. opens Cloudflare login when needed;
3. creates/reuses one Workers KV namespace;
4. creates/reuses one Queue with 24-hour retention;
5. writes the generated Wrangler configuration only to an ignored local file;
6. asks once for the narrow GitHub dispatch token;
7. generates a one-hour setup bootstrap secret locally;
8. stores the setup/dispatch values as Worker secrets;
9. deploys the Worker to `workers.dev`;
10. pins that exact `/tokens/github` endpoint into the repository's `CWB_TOKEN_ENDPOINT` Actions variable;
11. prints the protected GitHub App setup URL.

No GitHub App private key needs to be copied into PowerShell or ChatGPT.

## GitHub App registration

Open the setup URL printed by the script within one hour.

The URL keeps the bootstrap value in the browser fragment (`#token=...`), which is not sent in the HTTP request URL. The page sends it in a same-origin POST body and establishes a Secure/HttpOnly setup cookie.

Then:

1. review the preconfigured private development App;
2. select **Create GitHub App**;
3. let the callback store the generated credentials in Workers KV;
4. install the App on one **public** test repository;
5. push a commit or open/update a pull request.

If the App is later installed on a private repository, the free gateway returns an accepted-but-unsupported disposition and does not enqueue that repository into the public Actions worker.

The App itself keeps the minimum registration permissions:

- Checks: read/write
- Contents: read
- Pull requests: read

and subscribes only to `push` and `pull_request`.

## Expired setup link

If the one-hour setup window expires:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\cloudflare\rotate-setup-token.ps1
```

This rotates only the bootstrap secret. It does not replace the GitHub App credentials or rebuild the Queue/KV resources.

## Local generated files

The following files are intentionally ignored by Git:

- `deploy/cloudflare/wrangler.generated.json`
- `deploy/cloudflare/.worker-url`

They contain deployment metadata, not the GitHub App private key.
