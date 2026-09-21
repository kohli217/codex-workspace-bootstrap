# Ecosystem motivation

`codex-workspace-bootstrap` focuses on the repository layer: making project assumptions, local tooling, validation commands, and Codex instructions explicit and auditable.

It does **not** claim to fix Codex Desktop, WSL, sandbox, path-conversion, or app-server bugs.

## Why Windows-first?

Public reports in the OpenAI Codex repository show that Windows and Windows+WSL development can involve environment-boundary problems that are harder to reason about than a single native shell setup. Examples include:

- Windows Desktop + WSL integration gaps involving config, paths, state, plugins, execution, and recovery:
  https://github.com/openai/codex/issues/25216
- UNC working-directory, config-home, and worktree issues:
  https://github.com/openai/codex/issues/18506
- persisted WSL paths being interpreted as Windows drive paths:
  https://github.com/openai/codex/issues/42292
- broader discussion of project command-environment contracts and workspace bootstrap assumptions:
  https://github.com/openai/codex/discussions/26901

Those are upstream product issues. This project addresses a different but adjacent problem: repositories themselves often fail to state what tools, commands, safety constraints, and agent instructions are expected.

## What this project can improve

At the repository layer, the CLI can help maintainers make these facts visible:

- whether common development tools are available;
- whether repository guidance such as `AGENTS.md` exists;
- which common project manifests are present;
- whether risky filenames are tracked, ignored, or untracked when Git is available;
- which conservative validation commands should be considered for generated agent instructions;
- whether a repository can use the same audit in local development and CI.

This reduces ambiguity around project setup. It does not guarantee that Codex itself will select the correct runtime, shell, sandbox, or path mapping.

## Design principle

Prefer observable facts over environment guesses.

The audit reports what it can directly observe and keeps warnings separate from blocking findings. Generated instructions are intentionally conservative and are meant to be reviewed by maintainers.

## Why this matters for OSS maintenance

Maintainers need repeatable setup and review paths for human and agent-assisted contributions. A small, deterministic bootstrap layer can make issue work, pull-request review, CI, and release validation easier to reproduce across contributors and machines.
