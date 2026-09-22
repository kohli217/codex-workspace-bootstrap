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

## End-to-end flow

```text
GitHub push / pull_request
        ↓
prepare_github_app_event(...)
        ↓
normalize repository + head SHA + installation ID
        ↓
create installation access token
        ↓
checkout/read the exact target revision
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
