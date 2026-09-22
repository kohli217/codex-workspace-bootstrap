from pathlib import Path
import json

from codex_workspace_bootstrap.instructions import detect_instruction_signals, lint_instructions


def test_public_pattern_openai_codex_pnpm_repo_without_js_command_drift(tmp_path: Path) -> None:
    """Pattern observed in openai/codex at a6fdb11: AGENTS.md + pnpm packageManager."""
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10.34.5",
                "scripts": {"format": "prettier --check ."},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Run `just fmt` and `just argument-comment-lint` when relevant.\n",
        encoding="utf-8",
    )

    assert lint_instructions(tmp_path) == []


def test_public_pattern_cline_multi_instruction_bun_baseline_is_compatible(tmp_path: Path) -> None:
    """Pattern observed in Cline/Cline at ee46dc4: AGENTS + Copilot + Bun."""
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "bun@1.3.13",
                "scripts": {
                    "test:unit": "vitest run",
                    "compile": "node build.mjs",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "bun.lock").write_text("", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Use Bun only. Validate with `bun run test:unit`.\n",
        encoding="utf-8",
    )
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "copilot-instructions.md").write_text(
        "Tests: `bun run test:unit`. Build: `bun run compile`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "package-manager-mismatch" for item in findings)
    assert not any(item.kind == "package-manager-drift" for item in findings)
    assert not any(item.kind == "validation-command-drift" for item in findings)


def test_public_pattern_continue_gradle_rule_does_not_conflict_with_root_npm(tmp_path: Path) -> None:
    """Pattern observed in continuedev/continue at 5522c6f: scoped Gradle rule + root package.json."""
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"format": "prettier --write ."}}),
        encoding="utf-8",
    )
    rules = tmp_path / ".continue" / "rules"
    rules.mkdir(parents=True)
    (rules / "intellij-plugin-test-execution.md").write_text(
        "Run tests with `./gradlew test --tests ExampleTest`.\n",
        encoding="utf-8",
    )

    assert lint_instructions(tmp_path) == []


def test_public_pattern_vscode_brace_wrapped_apply_to_keeps_static_scope(tmp_path: Path) -> None:
    """Pattern observed in microsoft/vscode: brace-wrapped Copilot applyTo alternatives."""
    directory = tmp_path / ".github" / "instructions"
    directory.mkdir(parents=True)
    (directory / "writing-tests.instructions.md").write_text(
        "---\n"
        "description: Test guidance\n"
        'applyTo: "{src/vs/**/test/**,src/vs/**/*.test.ts,src/vs/**/*.integrationTest.ts}"\n'
        "---\n"
        "# Writing Tests\n",
        encoding="utf-8",
    )

    signals = detect_instruction_signals(tmp_path)
    signal = next(
        item
        for item in signals
        if item.path == ".github/instructions/writing-tests.instructions.md"
    )

    assert signal.kind == "path-specific"
    assert signal.scope == "src/vs"


def test_public_pattern_fit_framework_gemini_reads_agents_md(tmp_path: Path) -> None:
    """Pattern observed in ModelEngine-Group/fit-framework at e2f285d: Gemini reads AGENTS.md."""
    gemini = tmp_path / ".gemini"
    gemini.mkdir()
    (gemini / "settings.json").write_text(
        json.dumps({"context": {"fileName": ["AGENTS.md"]}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Validate with `mvn clean install`.\n",
        encoding="utf-8",
    )

    signals = detect_instruction_signals(tmp_path)

    assert any(
        item.tool == "Codex / OpenAI agents" and item.path == "AGENTS.md"
        for item in signals
    )
    assert any(
        item.tool == "Gemini CLI" and item.path == "AGENTS.md"
        for item in signals
    )
    assert not any(
        item.tool == "Gemini CLI" and item.path == "GEMINI.md"
        for item in signals
    )


def test_public_pattern_d3plus_workspace_filter_uses_workspace_script(tmp_path: Path) -> None:
    """Pattern observed in d3plus/d3plus at 2818442: root AGENTS targets @d3plus/core."""
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@11.10.0",
                "scripts": {
                    "test": "pnpm -r --if-present run test",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    core = tmp_path / "packages" / "core"
    core.mkdir(parents=True)
    (core / "package.json").write_text(
        json.dumps(
            {
                "name": "@d3plus/core",
                "scripts": {
                    "dev": "node ../../scripts/dev.js",
                    "test": "mocha",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run `pnpm --filter @d3plus/core run dev` for the core dev server.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_public_pattern_tracecat_directory_target_uses_frontend_package(tmp_path: Path) -> None:
    """Pattern observed in TracecatHQ/tracecat at 45eb759: root AGENTS targets frontend."""
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10.30.3",
                "scripts": {
                    "test": "jest",
                    "lint": "pnpm exec biome lint .",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Validate frontend changes with `pnpm -C frontend test`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)

