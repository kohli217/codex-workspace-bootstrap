# Roadmap

## Tracked next steps

- [#19 — Add Windows doctor command with non-destructive remediation guidance](https://github.com/kohli217/codex-workspace-bootstrap/issues/19)

This roadmap records intended work; it is not a promise of delivery dates.

## Near term

- add richer Python, Node.js, and mixed-project detection
- distinguish tracked and untracked secret-risk files using Git when available
- generate project-specific AGENTS.md templates
- add a `doctor` command with remediation guidance for Windows
- improve CI-oriented exit policies
- add install verification on clean Windows runners

## Later

- optional OpenAI API-assisted instruction drafting
- repository policy checks for maintainers
- safe GitHub Actions generation
- richer JSON/SARIF output for security tooling
- package distribution beyond direct GitHub installation

## Non-goals

- sending repository content to a remote service by default
- silently modifying project configuration
- claiming that a passing audit proves a repository is secure
