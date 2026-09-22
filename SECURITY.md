# Security Policy

## Supported versions

The latest release and the default branch receive security fixes.

## Reporting a vulnerability

Do not post credentials, tokens, private repository contents, proof-of-concept exploit details, or other sensitive vulnerability information in a public issue.

For a suspected vulnerability, use GitHub's **private vulnerability reporting** flow:

**Security and quality → Advisories → Report a vulnerability**

https://github.com/kohli217/codex-workspace-bootstrap/security/advisories/new

This creates a private report visible to the repository maintainers rather than a public issue.

For ordinary security-hardening suggestions that do not disclose a vulnerability, open a GitHub issue with a minimal reproducible description.

## What to include

When possible, include:

- the affected version or commit;
- the impact and expected behavior;
- minimal reproduction steps;
- relevant platform/runtime details;
- suggested remediation, if known.

Do not include real credentials, private repository contents, or unrelated sensitive data.

## Scope

The CLI performs local repository and toolchain inspection. The core audit path is designed not to transmit repository contents over the network. Repository instruction/configuration and project-marker inputs are not trusted through symbolic links, and write operations refuse symlinked `AGENTS.md` targets.

Secret-risk detection is filename-based and is not a replacement for dedicated secret or vulnerability scanners. A passing result is not a security guarantee.

## GitHub App credentials

The future GitHub App uses an App private key, a webhook secret, and short-lived installation access tokens. Treat all of them as credentials.

- Never commit a GitHub App private key, webhook secret, installation token, manifest-conversion response, or populated local environment file.
- Store the private key and webhook secret using a secret-management mechanism appropriate to the deployment platform.
- Keep the App registration on the documented minimum repository permissions: Checks read/write, Contents read-only, and Pull requests read-only.
- Verify every webhook with `X-Hub-Signature-256` before parsing or acting on its payload.
- Installation tokens should be created only for the installation that delivered the event and should not be logged. The worker further restricts each token to the single event repository and only the `contents:read` and `checks:write` permissions needed after webhook receipt.
- Pull request code is untrusted input. The GitHub App checkout path disables system/global Git configuration and Git hooks, does not initialize submodules, and never executes project validation commands from the checked-out repository.
- A dynamic branch or pull-request ref is accepted only when it resolves to the SHA expected from the webhook event.

The preferred zero-cost Cloudflare deployment stores Manifest-generated GitHub App credentials in Workers KV. Cloudflare encrypts all KV values at rest with AES-256 and protects transport with TLS. The App private key and webhook secret never enter the GitHub Actions runner.

The zero-cost deployment is public-repository-only. Private-repository webhook events are rejected at the Cloudflare gateway before queueing, preventing private repository names, SHAs, and code from entering a public GitHub Actions run.

The Cloudflare installation-token broker accepts GitHub Actions OIDC only after verifying GitHub's signature, an audience equal to the exact Worker `/tokens/github` endpoint that received the request, repository, main-branch ref, `workflow_dispatch` event, and exact `.github/workflows/github-app-worker.yml` workflow identity. It also requires an HMAC broker grant derived from the verified webhook secret and bound to the delivery ID plus the complete normalized scan target, including the commit SHA and pull-request/ref metadata. Tokens returned to Actions are limited to the single webhook repository and only `contents:read` + `checks:write`.

The Cloudflare workflow-dispatch credential must be a fine-grained personal access token restricted to `kohli217/codex-workspace-bootstrap` with Actions write only. It is uploaded once as the Worker secret `CWB_DISPATCH_TOKEN` and is never read back by the deployment script. The Worker uses it only to start the dedicated workflow dispatch. The token must never be committed or logged.

The reference Cloud Run deployment further separates credentials by service identity: the public ingress can read the webhook/setup secrets and add new Manifest-generated secret versions, while the private worker can read only the App client ID and private key. Pub/Sub invokes the worker through Cloud Run IAM rather than a public worker endpoint.

The Manifest setup endpoint requires a bootstrap token before it will render or accept a GitHub App registration callback. Setup tokens embed their issuance time and expire after one hour. The deployment prints the token in a URL fragment rather than a query string; browser fragments are not sent to Cloud Run. The bootstrap page POSTs the token in the request body, and only the verified server-side secret value is copied into a Secure/HttpOnly cookie. Response header values reject CR/LF characters.

The production image copies only the package metadata and `src/` tree, and `.dockerignore` excludes Git history, tests, local environments, reports, and common credential filenames from the Docker build context.

The repository ignores common private-key and local-secret filenames, but ignore rules are not a substitute for secure credential storage.
