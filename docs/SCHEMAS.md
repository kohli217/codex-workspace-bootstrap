# Machine-readable contracts

CWB exposes two versioned machine-readable contracts that integrations can depend on without importing private implementation details.

## Inspect the schemas

The installed CLI prints the current JSON Schema documents using only the Python standard library:

```powershell
cwb schema preflight
cwb schema config
```

The same documents are available to Python integrations:

```python
from codex_workspace_bootstrap.schemas import schema_document

preflight_schema = schema_document("preflight")
config_schema = schema_document("config")
```

The schema documents use JSON Schema Draft 2020-12.

## Preflight report v1

Every `build_preflight(...)` result contains:

```json
{
  "schema_version": 1
}
```

Version 1 keeps these top-level fields stable:

- `schema_version`
- `repository`
- `local_toolchain_checked`
- `state`
- `project_signals`
- `instruction_signals`
- `instruction_findings`
- `instruction_summary`
- `summary`
- `next_actions`
- `checks`

Optional fields may be added within schema v1. Current optional fields include repository configuration and suppression metadata.

A removal, incompatible type change, or intentional semantic break requires a new `PREFLIGHT_REPORT_SCHEMA_VERSION`.

Consumers should reject an unsupported schema version instead of guessing.

## Repository configuration v1

The optional repository-root `.cwb.json` uses:

```json
{
  "version": 1
}
```

Unlike the preflight report, repository configuration is intentionally closed: unknown keys are rejected by the parser.

The JSON Schema documents the public structure, but the CWB parser remains authoritative for safety rules that are narrower than generic schema validation. In particular, CWB additionally enforces:

- a regular, non-symlink root `.cwb.json`;
- a 64 KB file-size limit;
- exact repository-relative instruction paths;
- no wildcard, parent-traversal, or absolute instruction paths;
- non-empty suppression reasons;
- no suppression of blocking checks;
- no suppression of essential readiness checks;
- no suppression of tracked secret-risk findings;
- no suppression of error-severity instruction findings.

A future incompatible repository-policy format must increment `CONFIG_VERSION`.

## Compatibility policy toward v1.0

Before `v1.0.0`, schema version 1 is already treated as a compatibility boundary. The stabilization work leading to 1.0 is intended to remove ambiguity, not to churn the contract.

For the 1.x line:

- additive optional preflight fields may remain within preflight schema v1;
- breaking preflight changes require a new report schema version;
- incompatible `.cwb.json` changes require a new config version;
- existing version numbers are never silently reinterpreted;
- CLI, GitHub Action, GitHub App, and future agent adapters must consume the same shared preflight contract.

JSON Schema is documentation and interoperability metadata. It is not a security bypass: the implementation's fail-closed parser and policy evaluator remain authoritative.
