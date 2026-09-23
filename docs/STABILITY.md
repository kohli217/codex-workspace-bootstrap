# Stability and compatibility policy

This document defines the compatibility target for the CWB 1.x line.

CWB follows semantic versioning for public releases. The goal of `v1.0.0` is not to freeze detector coverage; it is to make the public interfaces predictable enough that repositories and integrations can upgrade without guessing what changed.

## Semantic versioning in 1.x

For releases after `v1.0.0`:

- **patch** releases (`1.x.y`) may fix bugs, false positives, documentation, security issues, and narrowly improve evidence-backed detection without intentionally breaking documented public interfaces;
- **minor** releases (`1.x.0`) may add commands, flags, optional report fields, detector coverage, adapters, and other backward-compatible behavior;
- **major** releases may make intentional breaking changes to documented CLI or machine-readable contracts.

Security fixes are the exception to preserving unsafe semantics. If behavior creates a concrete security boundary problem, a patch/minor release may tighten or reject that unsafe behavior rather than keep compatibility with it.

## CLI compatibility

The documented top-level commands and flags are public interfaces.

Within 1.x:

- existing commands and flags should keep their documented meaning;
- new optional commands and flags may be added in minor releases;
- removals or meaningfully incompatible flag changes should normally be deprecated before removal;
- exit-code behavior tied to `--strict`, `--fail-on-integrity`, and `--require-ready` is part of the public policy contract.

A bug fix that makes an option match its already-documented meaning is not treated as a compatibility break.

## Preflight report compatibility

The machine report has its own version:

```json
{
  "schema_version": 1
}
```

Within preflight schema version 1:

- required documented fields keep their types and meaning;
- new optional fields may be added;
- consumers should ignore optional fields they do not understand;
- removing a required field, changing its type incompatibly, or intentionally changing its semantics requires a new preflight schema version.

Inspect the current contract with:

```powershell
cwb schema preflight
```

## Repository configuration compatibility

Root `.cwb.json` also has an independent version:

```json
{
  "version": 1
}
```

Config version 1 remains fail-closed: unknown keys are rejected, and implementation safety checks remain authoritative.

An incompatible config-format change requires a new config version rather than silently changing the meaning of `version: 1`.

Inspect the current structure with:

```powershell
cwb schema config
```

## Detector evolution

Detector coverage is intentionally allowed to improve during 1.x.

A release may add a new evidence-backed warning or recognize a newly established agent-instruction format without incrementing the machine schema version when the report structure itself remains compatible.

New detection should continue to follow the project rule:

> public/reproducible repository evidence -> deterministic regression fixture -> implementation -> CI

CWB should prefer a missed warning over a speculative heuristic that creates noisy false positives.

## GitHub Action compatibility

For reproducible automation, pin the reusable Action to an immutable release tag such as:

```yaml
uses: kohli217/codex-workspace-bootstrap@v1.0.0
```

Repositories that deliberately want compatible 1.x updates may choose a broader update workflow, but CWB documentation uses exact release tags so changes are explicit.

The Action delegates to the same CLI/preflight contract. It should not invent a second READY / NEEDS ATTENTION / BLOCKED model.

## GitHub App compatibility

The GitHub App uses the shared repository-only preflight and GitHub Check adapter.

Within 1.x, App delivery changes may improve onboarding, reliability, annotations, and presentation without changing the underlying state meaning independently from the CLI/Action.

CWB should not widen GitHub App repository permissions merely to add convenience features.

## Deprecation

When practical, a documented user-facing behavior scheduled for removal should first:

1. remain functional;
2. emit or document a clear deprecation notice;
3. provide a replacement path;
4. be removed only in an appropriate breaking release.

Machine schema versions are not silently reinterpreted as a deprecation mechanism.

## Upgrade checklist

Before upgrading a pinned repository:

1. read the changelog entries between versions;
2. run `cwb preflight . --require-ready` locally or in CI;
3. if the repository uses `.cwb.json`, verify its version is still supported;
4. if another system consumes JSON output, verify `schema_version`;
5. review any newly surfaced warnings rather than suppressing them automatically.

A `READY` result means the repository satisfies the checks represented by the current CWB model. It does not prove the repository is secure.
