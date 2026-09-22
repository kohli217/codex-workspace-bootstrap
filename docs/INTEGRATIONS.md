# Integration contract

`codex-workspace-bootstrap` keeps repository analysis separate from delivery surfaces such as the CLI, GitHub Action, a future GitHub App, and future AI-agent skills.

The supported integration boundary is the preflight report plus the shared policy evaluator.

## Build a report

```python
from pathlib import Path

from codex_workspace_bootstrap.preflight import (
    PREFLIGHT_REPORT_SCHEMA_VERSION,
    build_preflight,
)

report = build_preflight(Path("."))
assert report["schema_version"] == PREFLIGHT_REPORT_SCHEMA_VERSION
assert report["local_toolchain_checked"] is True
```

The report is deterministic for the repository/toolchain evidence inspected by the core preflight. The core preflight does not send repository contents to a remote AI service.

## Report schema version

Every preflight report contains:

```json
{
  "schema_version": 1
}
```

Consumers should check `schema_version` before depending on report fields.

Within a schema version, new optional fields may be added. A change that intentionally breaks the machine-readable contract must increment `PREFLIGHT_REPORT_SCHEMA_VERSION`.

This makes it possible for integrations to reject an unsupported report version instead of silently misinterpreting it.

## Evaluate policy once

Delivery surfaces should not reimplement READY / NEEDS ATTENTION / BLOCKED gating.

Use the shared evaluator:

```python
from codex_workspace_bootstrap.preflight import evaluate_preflight_policy

decision = evaluate_preflight_policy(
    report,
    strict=True,
    fail_on_integrity=True,
    require_ready=False,
)

if decision.passed:
    print("pass")
else:
    print(decision.failures)
```

The current failure identifiers are:

- `blocking-findings` — `strict=True` and the preflight state is `BLOCKED`
- `instruction-integrity-findings` — `fail_on_integrity=True` and integrity findings exist
- `repository-not-ready` — `require_ready=True` and the state is not `READY`

The CLI uses this same evaluator. The reusable GitHub Action invokes the CLI, so it inherits the same policy behavior.

## Render a human-readable check summary

```python
from codex_workspace_bootstrap.preflight import render_markdown

summary = render_markdown(report)
```

A GitHub App can use the generated Markdown as the basis for a Check Run summary instead of inventing a second report format.

## Remote / GitHub App preflight

A remote scanner must not treat the scanner host's installed tools as repository evidence. Build the report in repository-only mode:

```python
report = build_preflight(
    Path("."),
    include_local_toolchain=False,
)
assert report["local_toolchain_checked"] is False
```

Repository-only mode still checks repository structure, project/package-manager evidence, AI instructions, Git tracking state, risky filenames, and instruction integrity. It skips availability/version probes for local tools such as Node.js, package managers, PowerShell, WSL, and Codex.

The CLI equivalent is `cwb preflight . --repository-only`.

## GitHub Check adapter

The package includes a network-free adapter that converts a supported preflight report into GitHub Check Run fields:

```python
from codex_workspace_bootstrap.integrations.github import build_github_check

check = build_github_check(
    report,
    strict=True,
    fail_on_integrity=True,
    require_ready=False,
)

fields = check.to_check_run_fields()
# A GitHub App adds its commit head_sha when creating the Check Run.
```

The adapter rejects unsupported `schema_version` values instead of silently interpreting them. Policy failures map to a `failure` conclusion, READY maps to `success`, and policy-allowed non-READY states map to `neutral`.

It performs no network requests and does not require GitHub credentials.

## GitHub webhook core

The package also includes a network-free webhook core for the App delivery layer:

```python
from codex_workspace_bootstrap.integrations.github_webhook import (
    normalize_github_webhook,
    should_run_github_preflight,
    verify_github_webhook_signature,
)

if not verify_github_webhook_signature(secret, raw_body, signature_header):
    raise PermissionError("invalid webhook signature")

target = normalize_github_webhook(event_name, payload)
if should_run_github_preflight(target):
    print(target.repository, target.head_sha)
```

The webhook core:

- verifies `X-Hub-Signature-256` with HMAC-SHA256 and constant-time comparison;
- normalizes supported `pull_request` and `push` payloads to repository + commit SHA;
- ignores pull-request actions that do not require a new scan;
- rejects deleted-ref pushes because they have no commit to inspect;
- performs no network requests and does not require GitHub credentials.

## GitHub App service core

Webhook delivery can use the network-free service core:

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

if decision.disposition == "scan":
    check = build_github_app_check(repository_root)
```

It handles signature verification, JSON parsing, ping/ignored/scan routing, and forces repository-only preflight semantics. Installation-token exchange, authenticated checkout, and Check Run publication remain outside this pure core.

## Secure GitHub checkout

A GitHub App can build a deterministic checkout plan from the normalized webhook target and fetch the exact revision without executing repository commands:

```python
from codex_workspace_bootstrap.integrations.github_checkout import (
    build_github_checkout_plan,
    checkout_github_repository,
)

plan = build_github_checkout_plan(target)
checkout = checkout_github_repository(
    plan,
    installation_token=installation_token,
    destination=temporary_repository_path,
)
```

Pull requests prefer GitHub's exact test merge SHA when present and safely fall back to the exact PR head. Pushes remain pinned to the webhook commit. Dynamic refs are accepted only when they resolve to the expected event SHA.

## GitHub delivery contract

GitHub authentication/request construction is represented without coupling the core to a particular HTTP or cryptography library:

```python
from codex_workspace_bootstrap.integrations.github_delivery import (
    build_check_run_request,
    build_github_app_jwt,
    build_installation_token_request,
)
```

The JWT builder accepts an injected RS256 signer. The REST request builders produce the exact method, URL, versioned GitHub headers, and JSON body for installation-token exchange and completed Check Run creation. Actual private-key loading and HTTP transport remain in the outer delivery shell.

## GitHub App registration contract

The minimum repository permissions and webhook subscriptions are also represented in code:

```python
from codex_workspace_bootstrap.integrations.github_app import (
    required_github_app_registration,
)

registration = required_github_app_registration()
```

The current contract is Checks write, Contents read, Pull requests read, with only `pull_request` and `push` webhook subscriptions. See [GITHUB_APP.md](GITHUB_APP.md) for the registration runbook.

## Intended GitHub App service

A future GitHub App should remain a thin delivery layer:

```text
GitHub webhook
    ↓
verify signature + normalize event
    ↓
obtain installation token + checkout/read repository
    ↓
build_preflight(..., include_local_toolchain=False)
    ↓
build_github_check(...)
    ↓
GitHub Check Run API
```

The App should not duplicate repository detection, instruction linting, readiness-state logic, policy gating, Check result mapping, or webhook routing rules.

## Intended AI-skill adapter

A future agent skill can use the same boundary:

```text
agent request
    ↓
build_preflight(...)
    ↓
evaluate_preflight_policy(..., require_ready=True)
    ↓
READY → continue
not READY → report findings before editing
```

Integrations must not treat READY as a security guarantee. It only means the repository satisfies the checks represented by the current preflight schema.
