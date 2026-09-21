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

The CLI performs local repository and toolchain inspection. The core audit path is designed not to transmit repository contents over the network. Repository instruction/configuration inputs are not read through symbolic links, and write operations refuse symlinked `AGENTS.md` targets.

Secret-risk detection is filename-based and is not a replacement for dedicated secret or vulnerability scanners. A passing result is not a security guarantee.
