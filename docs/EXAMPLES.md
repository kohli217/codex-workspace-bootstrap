# Examples

## 30-second repository audit

Install the pinned v0.1.0 wheel:

```powershell
py -m pip install "https://github.com/kohli217/codex-workspace-bootstrap/releases/download/v0.1.0/codex_workspace_bootstrap-0.1.0-py3-none-any.whl"
```

Then run:

```powershell
codex-workspace-bootstrap audit .
```

Typical output:

```text
Repository: C:\work\my-project
[PASS] git-repository: Git repository detected
[PASS] readme: README detected: README.md
[WARN] agents: AGENTS.md not found; run init-agents
[PASS] git: git version ...
[WARN] codex: codex command not found
[PASS] secret-risk-files: No common secret-bearing filenames detected
Summary: ... passed, ... warnings, 0 blocking
```

Warnings are informational unless a check is marked blocking.

## Generate Codex project instructions

```powershell
codex-workspace-bootstrap init-agents .
```

The generated `AGENTS.md` adapts to observable project signals such as `pyproject.toml`, a `tests/` directory, or `package.json`. Existing `AGENTS.md` files are not overwritten unless `--force` is explicitly supplied.

## CI gate

Use strict mode when you want tracked high-risk filenames to fail a build:

```powershell
codex-workspace-bootstrap audit . --strict
```

A tracked filename such as `.env` or a private-key-like file can become a blocking finding. The tool does not read or print the file contents.

## Machine-readable report

```powershell
codex-workspace-bootstrap audit . --json audit-report.json
```

The report includes each check and a summary, making it suitable for wrappers and maintainer automation.

## Check installed version

```powershell
codex-workspace-bootstrap --version
```
