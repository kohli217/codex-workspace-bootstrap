from pathlib import Path
import json

from codex_workspace_bootstrap.instructions import detect_instruction_signals, extract_commands, lint_instructions


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


def test_public_pattern_warp_yarn_inline_cwd_uses_website_package(tmp_path: Path) -> None:
    """Pattern observed in broadinstitute/warp at 8005650: inline Yarn cwd targets website."""
    website = tmp_path / "website"
    website.mkdir()
    (website / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "start": "docusaurus start",
                    "build": "docusaurus build",
                }
            }
        ),
        encoding="utf-8",
    )
    instruction_text = (
        "Preview with `yarn --cwd=website start` and validate with "
        "`yarn --cwd=website build`.\n"
    )
    (tmp_path / "AGENTS.md").write_text(instruction_text, encoding="utf-8")

    commands = extract_commands(instruction_text)
    findings = lint_instructions(tmp_path)

    assert "yarn --cwd=website start" in commands
    assert "yarn --cwd=website build" in commands
    assert not any(item.kind == "missing-package-script" for item in findings)


def test_public_pattern_wordpress_npm_post_script_workspace_uses_workspace_script(
    tmp_path: Path,
) -> None:
    """Pattern observed in WordPress/pattern-directory at 4482f38."""
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "wporg-pattern-directory-project",
                "private": True,
                "scripts": {
                    "test:php": "wp-env run phpunit",
                },
                "workspaces": [
                    "public_html/wp-content/plugins/pattern-creator",
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")
    creator = (
        tmp_path
        / "public_html"
        / "wp-content"
        / "plugins"
        / "pattern-creator"
    )
    creator.mkdir(parents=True)
    (creator / "package.json").write_text(
        json.dumps(
            {
                "name": "wporg-pattern-creator",
                "scripts": {
                    "test:unit": "wp-scripts test-unit-js",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run JS tests with "
        "`npm run test:unit --workspace=wporg-pattern-creator`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_public_pattern_vtex_claude_alias_reuses_regular_agents(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Pattern observed in vtex/address-form at 2643de3: CLAUDE.md -> AGENTS.md."""
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "Use Yarn. Validate with `yarn test`.\n",
        encoding="utf-8",
    )
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("AGENTS.md", encoding="utf-8")

    original_is_symlink = Path.is_symlink
    original_readlink = Path.readlink

    def fake_is_symlink(path: Path) -> bool:
        if path == claude:
            return True
        return original_is_symlink(path)

    def fake_readlink(path: Path) -> Path:
        if path == claude:
            return Path("AGENTS.md")
        return original_readlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "readlink", fake_readlink)

    signals = detect_instruction_signals(tmp_path)
    pairs = {(item.tool, item.path, item.kind) for item in signals}

    assert ("Codex / OpenAI agents", "AGENTS.md", "repository") in pairs
    assert ("Claude Code", "CLAUDE.md", "alias") in pairs


def test_public_pattern_cissp_shared_claude_and_gemini_aliases(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Pattern observed in kickflip-labs/cissp-study-hub at 1f92eb8."""
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "Shared repository guidance.\n",
        encoding="utf-8",
    )
    claude = tmp_path / "CLAUDE.md"
    gemini = tmp_path / "GEMINI.md"
    claude.write_text("AGENTS.md", encoding="utf-8")
    gemini.write_text("AGENTS.md", encoding="utf-8")

    original_is_symlink = Path.is_symlink
    original_readlink = Path.readlink

    def fake_is_symlink(path: Path) -> bool:
        if path in {claude, gemini}:
            return True
        return original_is_symlink(path)

    def fake_readlink(path: Path) -> Path:
        if path in {claude, gemini}:
            return Path("AGENTS.md")
        return original_readlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "readlink", fake_readlink)

    signals = detect_instruction_signals(tmp_path)
    pairs = {(item.tool, item.path, item.kind) for item in signals}

    assert ("Codex / OpenAI agents", "AGENTS.md", "repository") in pairs
    assert ("Claude Code", "CLAUDE.md", "alias") in pairs
    assert ("Gemini CLI", "GEMINI.md", "alias") in pairs


def test_public_pattern_unraid_pnpm_exact_path_filter_uses_api_package(
    tmp_path: Path,
) -> None:
    """Pattern observed in unraid/api at d061525: root AGENTS targets ./api."""
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "unraid-monorepo",
                "private": True,
                "packageManager": "pnpm@10.15.0",
                "scripts": {
                    "test": "pnpm -r test",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (tmp_path / "pnpm-workspace.yaml").write_text(
        'packages:\n  - "./api"\n',
        encoding="utf-8",
    )
    api = tmp_path / "api"
    api.mkdir()
    (api / "package.json").write_text(
        json.dumps(
            {
                "name": "@unraid/api",
                "scripts": {
                    "test": "NODE_ENV=test vitest run",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Run tests with: `pnpm --filter ./api test`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_public_pattern_deer_flow_cd_frontend_uses_frontend_package(
    tmp_path: Path,
) -> None:
    """Pattern observed in bytedance/deer-flow at 5335228: root AGENTS changes cwd."""
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps(
            {
                "name": "deer-flow-frontend",
                "packageManager": "pnpm@10.26.2",
                "scripts": {
                    "check": "eslint . --ext .ts,.tsx && tsc --noEmit",
                    "test": "rstest",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Frontend validation:\n"
        "```bash\n"
        "cd frontend && pnpm check\n"
        "cd frontend && pnpm test\n"
        "```\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_public_pattern_coral_npm_post_script_prefix_uses_coral_ui(
    tmp_path: Path,
) -> None:
    """Pattern observed in withcoral/coral at 2c58881: npm prefix follows script."""
    app = tmp_path / "apps" / "coral-ui"
    app.mkdir(parents=True)
    (app / "package.json").write_text(
        json.dumps(
            {
                "name": "coral-ui",
                "scripts": {
                    "build": "npm run proto:gen && react-router build",
                    "typecheck": "npm run proto:gen && react-router typegen && tsc",
                    "test": "npm run proto:gen && vitest run",
                    "check": "oxfmt --check && oxlint --deny-warnings",
                    "test:server": "node --test server.test.mjs",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Coral UI changes must pass "
        "`npm run check --prefix apps/coral-ui`, "
        "`npm run typecheck --prefix apps/coral-ui`, "
        "`npm test --prefix apps/coral-ui`, and "
        "`npm run build --prefix apps/coral-ui`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_public_pattern_marktoflow_pnpm_post_script_filter_uses_workspace(
    tmp_path: Path,
) -> None:
    """Pattern observed in marktoflow/marktoflow at 707a57c."""
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "marktoflow",
                "packageManager": "pnpm@9.15.0",
                "scripts": {
                    "test": "turbo run test",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    for name in ("core", "integrations"):
        package = tmp_path / "packages" / name
        package.mkdir(parents=True)
        (package / "package.json").write_text(
            json.dumps(
                {
                    "name": f"@marktoflow/{name}",
                    "scripts": {
                        "test": "vitest run",
                    },
                }
            ),
            encoding="utf-8",
        )
    (tmp_path / "AGENTS.md").write_text(
        "Core only: `pnpm test --filter=@marktoflow/core`.\n"
        "Integrations only: `pnpm test --filter=@marktoflow/integrations`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_public_pattern_react_auth_pnpm_recursive_skips_root_script_requirement(
    tmp_path: Path,
) -> None:
    """Pattern observed in forwardsoftware/react-auth at a5fdca1."""
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@12.4.0",
                "scripts": {},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    for directory, name in (
        ("lib", "@forward-software/react-auth"),
        ("packages/apple-signin", "@forward-software/react-auth-apple"),
        ("packages/google-signin", "@forward-software/react-auth-google"),
    ):
        package = tmp_path / directory
        package.mkdir(parents=True)
        (package / "package.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "scripts": {
                        "test": "vitest",
                    },
                }
            ),
            encoding="utf-8",
        )
    (tmp_path / "AGENTS.md").write_text(
        "Run all tests with `pnpm -r test`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)


def test_public_pattern_private_hosting_npm_workspaces_skips_root_script_requirement(
    tmp_path: Path,
) -> None:
    """Pattern observed in KutyAI/Private-Hosting-App at 9aa90fb."""
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "mc-hosting-platform",
                "workspaces": ["apps/*", "packages/*"],
                "scripts": {
                    "build": "npm run build --workspaces",
                },
            }
        ),
        encoding="utf-8",
    )
    packages = (
        ("apps/backend-api", "@mc-host/backend-api", "jest --passWithNoTests"),
        ("apps/desktop-ui", "@mc-host/desktop-ui", "vitest run"),
        ("apps/host-agent", "@mc-host/host-agent", "jest --passWithNoTests"),
        (
            "apps/relay-service",
            "@mc-host/relay-service",
            'echo "No tests declared for relay-service"',
        ),
        ("packages/shared-types", "@mc-host/shared-types", "jest --passWithNoTests"),
    )
    for directory, name, test_script in packages:
        package = tmp_path / directory
        package.mkdir(parents=True)
        (package / "package.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "scripts": {
                        "test": test_script,
                    },
                }
            ),
            encoding="utf-8",
        )
    (tmp_path / "AGENTS.md").write_text(
        "Run all tests with `npm test --workspaces`.\n",
        encoding="utf-8",
    )

    findings = lint_instructions(tmp_path)

    assert not any(item.kind == "missing-package-script" for item in findings)

