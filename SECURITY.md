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

- Never commit a GitHub App private key, webhook secret, installation token, or populated local environment file.
- Store the private key and webhook secret using a secret-management mechanism appropriate to the deployment platform.
- Keep the App registration on the documented minimum repository permissions: Checks read/write, Contents read-only, and Pull requests read-only.
- Verify every webhook with `X-Hub-Signature-256` before parsing or acting on its payload.
- Installation tokens should be created only for the installation that delivered the event and should not be logged. The worker further restricts each token to the single event repository and only the `contents:read` and `checks:write` permissions needed after webhook receipt.
- Pull request code is untrusted input. The GitHub App checkout path disables system/global Git configuration and Git hooks, does not initialize submodules, and never executes project validation commands from the checked-out repository.
- A dynamic branch or pull-request ref is accepted only when it resolves to the SHA expected from the webhook event.

The repository ignores common private-key and local-secret filenames, but ignore rules are not a substitute for secure credential storage.
