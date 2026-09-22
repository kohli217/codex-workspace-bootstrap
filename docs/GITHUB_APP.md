# GitHub App registration

This document defines the GitHub-side registration settings for the `codex-workspace-bootstrap` GitHub App.

The application service should remain a thin adapter over the existing preflight, webhook, policy, and Check Run code. Do not add repository permissions that are not required by the documented flow.

## Preferred development registration: App Manifest

For the development App, prefer GitHub's App Manifest flow instead of manually re-entering permissions and events. GitHub's manifest flow lets the registration page inherit CWB's code-level settings and generates the App private key and webhook secret after creation.

```python
from codex_workspace_bootstrap.integrations.github_manifest import (
    build_manifest_registration,
    render_manifest_registration_form,
)

registration = build_manifest_registration(
    base_url="https://YOUR-DEPLOYED-SERVICE",
)

html_form = render_manifest_registration_form(registration)
```

The form POSTs the JSON manifest to GitHub's personal App registration endpoint. GitHub redirects back to `/setup/github/callback` with a temporary `code` and the initiating `state`.

The callback must:

1. verify the returned `state` against the initiating value;
2. exchange `code` through `POST /app-manifests/{code}/conversions`;
3. immediately store the returned private key and webhook secret in the deployment secret store;
4. avoid logging or returning either secret;
5. finish the manifest handshake within GitHub's one-hour limit.

The generated development manifest defaults to `public=false`. Marketplace/public-App registration should be a separate promotion step after end-to-end validation.

## Minimum repository permissions

Configure these under **Repository permissions**:

| Permission | Access | Why it is needed |
| --- | --- | --- |
| Checks | Read and write | Create the CWB Check Run result for the inspected commit. |
| Contents | Read-only | Receive `push` events and read/checkout the repository revision that will be inspected. |
| Pull requests | Read-only | Receive `pull_request` events and identify the PR head commit to inspect. |

Do not grant write access to repository contents or pull requests for the initial App. CWB does not need to modify user repositories to perform preflight checks.

The machine-readable source of truth is:

```python
from codex_workspace_bootstrap.integrations.github_app import (
    required_github_app_registration,
)

registration = required_github_app_registration()
```

## Webhook events

Subscribe only to:

- **Pull request**
- **Push**

The webhook core currently triggers scans for:

- pull request `opened`
- pull request `reopened`
- pull request `synchronize`
- pull request `ready_for_review`
- non-deletion pushes

Other pull-request actions are accepted by the normalizer but do not trigger a scan.

## Registration settings for the first development App

For the first private development installation:

- **GitHub App name:** choose a unique development name, for example `CWB Preflight Dev`
- **Homepage URL:** `https://github.com/kohli217/codex-workspace-bootstrap`
- **Webhooks:** Active
- **Webhook URL:** use the HTTPS endpoint of the App service once it is deployed
- **Webhook secret:** use a new high-entropy secret; never commit it
- **Where can this GitHub App be installed?:** keep the development App limited to the maintainer account until end-to-end behavior has been validated
- **User authorization / OAuth callback:** not required for the initial installation-token flow

Generate a private key only after the App has been created and the service has somewhere secure to store it.

## Required service secrets

A deployed App service needs:

- GitHub App ID
- GitHub App private key
- webhook secret

A webhook payload sent to a GitHub App includes the installation ID. The service can combine that installation ID with an App JWT to request an installation access token.

Never commit the private key, webhook secret, installation token, or a populated local environment file.

The repository already ignores `*.pem`, `*.key`, `.env`, and `.env.*` (except the template file).

## Service-core API

The network-free service core joins webhook verification/routing with repository-only preflight and Check rendering:

```python
from codex_workspace_bootstrap.integrations.github_app_service import (
    build_github_app_check,
    prepare_github_app_event,
)

decision = prepare_github_app_event(
    event_name=event_name,
    raw_body=raw_body,
    signature_header=signature_header,
    webhook_secret=webhook_secret,
)

if decision.disposition == "ping":
    # Respond successfully to GitHub's webhook ping.
    ...
elif decision.disposition == "ignored":
    # Valid event, but no scan is needed.
    ...
else:
    # After authenticated checkout of decision.target.head_sha:
    check = build_github_app_check(repository_root)
```

This API performs no HTTP requests and does not exchange GitHub credentials. The outer delivery service remains responsible for installation authentication, checkout, and posting the Check Run.

## Secure repository checkout

The App should inspect the exact webhook revision without executing repository code:

```python
from codex_workspace_bootstrap.integrations.github_checkout import (
    build_github_checkout_plan,
    checkout_github_repository,
)

plan = build_github_checkout_plan(decision.target)
checkout = checkout_github_repository(
    plan,
    installation_token=installation_token,
    destination=temporary_repository_path,
)

check = build_github_app_check(checkout.root)
```

For pull requests, the checkout plan prefers the exact GitHub test merge commit when `merge_commit_sha` is available. This matches GitHub's normal pull-request CI model. If GitHub has not produced a test merge commit, it falls back to the exact webhook head commit. The base repository's pull refs provide a fallback for fork pull requests without requiring credentials for the contributor's fork.

For pushes, the exact webhook commit is preferred. Any ref fallback must resolve to that same SHA or the checkout is rejected.

Checkout hardening:

- the installation token is supplied through Git configuration environment values, never a command-line argument;
- interactive Git credential prompts are disabled;
- system and global Git configuration are disabled for the checkout subprocesses;
- Git hooks are redirected to an empty temporary directory;
- submodules are not initialized;
- no project, build, test, package-manager, or instruction-file command is executed.

Use `checkout.commit_sha` as the SHA for the resulting Check Run. This ensures the Check describes the exact tree CWB inspected.

## Delivery contract

The package also defines the GitHub REST delivery contract without adding an HTTP or crypto dependency:

```python
from codex_workspace_bootstrap.integrations.github_delivery import (
    build_check_run_request,
    build_github_app_jwt,
    build_installation_token_request,
)

app_jwt = build_github_app_jwt(
    client_id=client_id,
    now=unix_time,
    signer=rs256_signer,
)

token_request = build_installation_token_request(
    installation_id=installation_id,
    app_jwt=app_jwt,
)

check_request = build_check_run_request(
    repository=target.repository,
    head_sha=target.head_sha,
    installation_token=installation_token,
    check=check,
)
```

The injected `rs256_signer` must sign the provided JWT signing input using RSA PKCS#1 v1.5 with SHA-256. GitHub requires RS256 for App JWTs. The contract sets `iat` 60 seconds in the past, keeps `exp` within 10 minutes, and uses the App client ID as `iss`.

The request builders currently target GitHub REST API version `2026-03-10` and send `User-Agent: codex-workspace-bootstrap`, which is required for GitHub REST API requests.

## Worker runtime

The package now contains a synchronous **worker** runtime for one already-accepted scan event:

```python
from codex_workspace_bootstrap.integrations.github_runtime import (
    execute_github_scan,
)

result = execute_github_scan(
    target,
    client_id=github_app_client_id,
    private_key_path=private_key_path,
)
```

The worker:

1. signs the GitHub App JWT with OpenSSL/RS256;
2. requests an installation token scoped to only the event repository and only `contents:read` + `checks:write`;
3. performs the hardened exact-revision checkout;
4. for queued deliveries, checks whether the same GitHub delivery ID already has a completed CWB Check Run on that exact commit;
5. runs repository-only CWB preflight only when the delivery is new;
6. creates the completed GitHub Check Run for the exact inspected commit, storing the delivery ID as `external_id`.

This makes normal Pub/Sub/GitHub redelivery idempotent: an already-completed delivery is reused instead of producing another scan and Check Run. It is intentionally a completed-result deduplication guard, not a distributed lock for two copies that begin at exactly the same time.

The runtime uses Python's standard-library HTTPS client. It does not depend on PyJWT, cryptography, requests, or a web framework. Installation token parsing intentionally does not assume a fixed token length or legacy token format.

**Do not run this full worker inline before acknowledging the webhook.** GitHub expects webhook servers to return a 2xx response within 10 seconds. Production ingress should verify/rout the webhook, enqueue the normalized target, return 2xx, and let this worker perform checkout/scanning/API calls separately.

## Preferred zero-cost deployment: Cloudflare + GitHub Actions

For development and low-volume public OSS use, the preferred deployment is [deploy/cloudflare](../deploy/cloudflare/README.md).

```text
GitHub webhook
  -> Cloudflare Worker
  -> Cloudflare Queue
  -> CWB public-repository GitHub Actions worker
  -> OIDC-authenticated installation-token broker
  -> secure exact-revision checkout
  -> CWB Check Run
```

This design avoids a Google Cloud billing account. The ingress, durable queue, state storage, and broker use Cloudflare's Free plan, while the scan runs on standard GitHub-hosted Actions runners in this public repository.

The zero-cost path is **public-repository-only**. The Cloudflare gateway rejects private-repository events before queueing so private repository metadata and code are never exposed to the public Actions worker.

The Cloudflare Worker receives the App Manifest callback and stores the generated client ID, private key, and webhook secret in Workers KV. Cloudflare encrypts KV values at rest. The GitHub Actions runner never receives the App private key or webhook secret.

For each scan, Cloudflare passes its own `https://*.workers.dev/tokens/github` endpoint into the dedicated workflow dispatch. GitHub Actions requests an OIDC token with that exact endpoint as the audience. The broker accepts only OIDC tokens whose audience equals the Worker endpoint receiving the request, and only for `kohli217/codex-workspace-bootstrap`, `refs/heads/main`, the `workflow_dispatch` event, and the exact `.github/workflows/github-app-worker.yml` workflow. The request must also carry an HMAC broker grant created from the verified webhook and bound to the exact normalized scan target, including its commit SHA. Only then does the broker return a short-lived installation token scoped to the single event repository with only `contents:read` and `checks:write`.

Cloudflare Queue remains in front of GitHub Actions because GitHub does not automatically redeliver failed webhook deliveries. If workflow dispatch is temporarily unavailable, the queue consumer retries instead of dropping the event.

## Cloud Run + Pub/Sub deployment

A deployable production shell is available in [deploy/cloudrun](../deploy/cloudrun/README.md).

It uses two Cloud Run services built from the same container:

- a public `ingress` service that verifies GitHub signatures, handles the protected App Manifest setup flow, and publishes normalized scan targets;
- a private `worker` service invoked only through authenticated Pub/Sub push delivery.

The ingress does not receive the GitHub App private key. The worker does not receive the webhook secret or Manifest setup token.

The Manifest callback stores the generated client ID, private key, and webhook secret directly into Secret Manager. The private key and client ID are mounted only into the worker, while the webhook secret is mounted only into the ingress.

The deployment script creates dedicated service identities and an authenticated Pub/Sub push subscription. A failed worker response remains retryable through Pub/Sub instead of being lost in an in-memory background task.

The one-time setup link carries its bootstrap secret in the browser URL fragment, not the HTTP query string. The fragment is converted into a same-origin POST body before the ingress establishes the Secure/HttpOnly setup session, keeping the bootstrap secret out of Cloud Run request URLs.

## End-to-end flow

```text
GitHub push / pull_request
        ↓
prepare_github_app_event(...)
        ↓
enqueue normalized scan target + return 2xx
        ↓
worker: create repository-scoped installation access token
        ↓
secure checkout of the exact webhook revision
        ↓
build_preflight(..., include_local_toolchain=False)
        ↓
build_github_check(...)
        ↓
POST GitHub Check Run
```

Repository analysis and policy behavior must continue to come from the shared core rather than being reimplemented by the web service.

The App service must use repository-only preflight mode. Local tool availability on the App host is deployment infrastructure, not evidence about the inspected repository.

## Promoting a verified development App to public

Promote the **existing** development App after a real installed-repository end-to-end run has reached a completed CWB Check Run. Do not create a second App or rotate the App private key/webhook secret solely for promotion.

GitHub supports changing an existing App's name, description, permissions, webhook subscriptions, and visibility after registration. The promotion sequence is:

1. Open **Settings → Developer settings → GitHub Apps → Edit** for the verified App.
2. Under **Basic information**, replace the generated development name with a stable public-facing name. Keep the existing homepage URL, webhook URL, and callback URL unchanged, then save.
3. Under **Permissions & events**, verify that repository permissions are still exactly:
   - **Checks:** Read and write
   - **Contents:** Read-only
   - **Pull requests:** Read-only
4. Under **Subscribe to events**, keep only:
   - **Push**
   - **Pull request**
5. Open **Advanced**. In **Danger zone**, choose **Make public**.
6. Open the App's **Public page**, choose **Install**, and use that page's installation link when sharing the App.

GitHub Marketplace publication is optional; a public GitHub App can be shared directly through its installation link without a Marketplace listing.

Important boundaries:

- A public App can be installed by other GitHub users and organizations. Once it is installed on other accounts, GitHub does not allow it to be made private again until those external installations are removed.
- Making the App public does **not** change the CWB free deployment's privacy boundary. The Cloudflare Free gateway still rejects private-repository events before queueing.
- Making the App public does **not** increase repository permissions. Do not add contents write, pull-request write, organization, or account permissions for the current CWB flow.
- Renaming or changing visibility does not require new Manifest-generated credentials; the deployed service continues to use the existing App identity and stored credentials.
- Free-tier quotas remain the operational ceiling. This deployment must not opt into a paid Cloudflare Workers plan merely because more public repositories install the App.

GitHub references:

- [Modifying a GitHub App registration](https://docs.github.com/en/apps/maintaining-github-apps/modifying-a-github-app-registration)
- [Making a GitHub App public or private](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/making-a-github-app-public-or-private)
- [Sharing your GitHub App](https://docs.github.com/en/apps/sharing-github-apps/sharing-your-github-app)

## Manual boundary

With the preferred free deployment and App Manifest flow, the authenticated GitHub action is reduced to creating the narrowly scoped workflow-dispatch token once, reviewing/naming the preconfigured development App, clicking **Create GitHub App**, and installing it on the selected test repository. The Manifest callback now carries an HMAC-signed one-hour `state`, avoiding reliance on callback cookies after the GitHub round trip. The manifest callback can receive GitHub's generated private key and webhook secret automatically.

Those credentials must never be pasted into an issue, pull request, committed file, or public chat. The deployed callback must put them directly into its deployment secret store before any real webhook processing begins.
