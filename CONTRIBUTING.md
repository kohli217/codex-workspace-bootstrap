# Contributing

Thank you for considering a contribution.

## Development setup

On Windows PowerShell:

```powershell
git clone https://github.com/kohli217/codex-workspace-bootstrap.git
cd codex-workspace-bootstrap
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

For tests:

```powershell
python -m pip install pytest
pytest
```

## Pull requests

- keep the change focused;
- add tests for behavior changes;
- preserve Python 3.10+ compatibility;
- preserve Windows behavior;
- do not include credentials, private repository data, or generated environment files;
- update documentation when user-facing behavior changes.

## Good first contributions

Start with the repository's [good first issues](https://github.com/kohli217/codex-workspace-bootstrap/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).

The smallest useful contribution is usually one of:

- add a regression fixture from one public repository layout;
- add one reproducible documentation example;
- improve a confusing error or remediation message;
- add a focused test for an existing detector.

If you are unsure whether an idea fits, comment on the issue before implementing. Keep pull requests focused and avoid bundling unrelated cleanup.

## AI-assisted contributions

AI-assisted contributions are welcome. Contributors remain responsible for reviewing generated code, tests, licenses, security implications, and final diffs before submission.


## Reporting false positives

False positives are high-value reports because this project is intentionally conservative.

Use the [False positive report](https://github.com/kohli217/codex-workspace-bootstrap/issues/new?template=false_positive.yml) template when `cwb` reports a finding that does not match the repository's intended setup.

You can report behavior from a private repository without naming or exposing it. Do not paste credentials, secret values, proprietary source code, or private repository contents. A minimal synthetic reproduction is preferred when possible.
