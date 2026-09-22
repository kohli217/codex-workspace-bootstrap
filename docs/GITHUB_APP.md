# GitHub App registration

This document defines the GitHub-side registration settings for the future `codex-workspace-bootstrap` GitHub App.

The application service should remain a thin adapter over the existing preflight, webhook, policy, and Check Run code. Do not add repository permissions that are not required by the documented flow.

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

The eventual service needs:

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
4. runs repository-only CWB preflight;
5. creates the completed GitHub Check Run for the exact inspected commit.

The runtime uses Python's standard-library HTTPS client. It does not depend on PyJWT, cryptography, requests, or a web framework. Installation token parsing intentionally does not assume a fixed token length or legacy token format.

**Do not run this full worker inline before acknowledging the webhook.** GitHub expects webhook servers to return a 2xx response within 10 seconds. Production ingress should verify/rout the webhook, enqueue the normalized target, return 2xx, and let this worker perform checkout/scanning/API calls separately.

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

## Manual boundary

Creating the GitHub App registration, generating its private key, choosing a webhook secret, and initially installing the App require an authenticated GitHub account action. Those credentials must not be pasted into an issue, pull request, committed file, or public chat.

After those values exist, the remaining service/authentication wiring can be implemented and tested against the development installation.
