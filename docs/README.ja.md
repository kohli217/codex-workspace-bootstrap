# codex-workspace-bootstrap 日本語ガイド

**AIコーディングエージェントにリポジトリを触らせる前のpreflightツール**です。

Windows-first、ローカル実行中心、CI対応。Codexだけでなく、Copilot / Cline / Claude Code / Gemini CLI / Continue / Cursor系の指示ファイルを横断し、存在確認だけでなく指示間のdriftも検出します。

> コミュニティ運営のOSSです。OpenAI公式製品ではありません。

## まずこれだけ

```powershell
py -m pip install codex-workspace-bootstrap
cwb preflight .
```

結果は次の3状態です。

- **READY**: 基本的なRepo準備とAI指示が確認でき、blocking項目なし
- **NEEDS ATTENTION**: 使用可能だが、重要な準備不足あり
- **BLOCKED**: 追跡済みsecret-riskファイル名など、先に確認すべきblocking項目あり

preflightは、次に何をすべきかをP0/P1/P2の優先度付きで表示します。

## 何を確認するか

- Git repository / README / LICENSE / .gitignore
- Python / Node.js / Go / Rust / JVM / .NET の代表的なproject manifest
- Git / Python / Node.js / Repoで選択されたpackage manager / PowerShell / WSL / Codex
- AGENTS.md
- GitHub Copilot repository instructions
- Cline / Claude Code / Gemini CLI / Continue / Cursor系の指示ファイル
- .env / `.env.production` などの環境別 `.env.*` / private-key系などsecret-riskになりやすいファイル名（`.env.example` などの一般的なテンプレート名は除外）
- Git追跡済み / ignore済み / untrackedの区別

さらに、packageManager / lockfile / package.json scriptsを根拠に、AI指示間のpackage manager不一致、存在しないscript、test/lint/build/typecheck/check系コマンドの食い違いを保守的に検出します。Pythonでは `ruff check` / `mypy` / `pyright` / `tox` / `nox` / `pre-commit run` を認識し、対応可能な `python -m` / `uv run` / `poetry run` / `pdm run` 形式も同一toolとして正規化します。ネストされた `AGENTS.md` / `AGENTS.override.md` / `CLAUDE.md` / `GEMINI.md` と、Copilotの `applyTo` やruleの `globs` から適用scopeも判定し、別scopeの指示を無理に矛盾扱いしません。

Secret候補のファイル内容は表示しません。

## 主なコマンド

```powershell
cwb preflight .
cwb doctor .
cwb audit .
cwb init-agents .
cwb fix .
```

Markdownレポート:

```powershell
cwb preflight . --markdown preflight.md
```

JSON:

```powershell
cwb preflight . --json preflight.json
```

SARIF:

```powershell
cwb preflight . --sarif preflight.sarif
```

## 意図した警告を安全に抑制する

Repo固有の事情で、既知の非blocking警告を意図的に許容したい場合は、Repo rootに `.cwb.json` を置けます。

```json
{
  "version": 1,
  "suppress": {
    "checks": [
      {
        "name": "license",
        "reason": "この内部Repoでは単独のLICENSEを置かない運用です。"
      }
    ],
    "instruction_findings": [
      {
        "kind": "validation-command-drift",
        "path": "CLAUDE.md",
        "scope": ".",
        "reason": "Claudeでは意図的に軽量なsmoke testだけを実行します。"
      }
    ]
  }
}
```

抑制はfail-closedです。すべての抑制に理由が必要で、instruction findingは正確なRepo相対パスを指定します。適用済み・未使用の抑制はpreflight reportに残るため、黙って消えることはありません。

次は抑制できません。

- blocking check
- Git repository / README / .gitignore / project manifestなどREADY判定の必須check
- tracked secret-risk finding
- wildcardを使った広いpath指定
- error severityのinstruction finding

不正または危険な `.cwb.json` は無視して続行せず、preflightを `NEEDS ATTENTION` にします。なお `cwb audit` は生の診断結果を確認するため、意図的に抑制を適用しません。抑制はCLI / GitHub Action / GitHub Appが共有する `preflight` 契約に適用されます。`.cwb.json` は検査対象revisionのRepo policyとして評価されるため、変更はCI設定やbranch policyと同様にレビューしてください。実際に抑制が適用された場合、GitHub Checkは `.cwb.json` にnotice annotationを表示します。

## AGENTS.md生成

```powershell
cwb init-agents .
```

Python / Node.js / Go / Rust / JVM / .NET のproject rootを識別し、検証コマンドはRepo内の直接的な根拠があるものだけを確定扱いします。Python/Nodeではpyproject.toml、pytest設定、package.jsonのpackageManager/lockfile、script名、READMEに書かれた検証コマンドを照合し、根拠が弱いコマンドはreview-requiredとして分離します。

## GitHub Actions

GitHub Marketplaceの再利用可能Actionとして利用できます。preflight MarkdownレポートはGitHub Actionsの**Job Summary**に表示されます。

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
- uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
  with:
    python-version: "3.13"
- uses: kohli217/codex-workspace-bootstrap@v0.10.0
  with:
    path: .
    strict: "true"
    fail_on_integrity: "true"
    require_ready: "true"
```

## 他ツールとの役割分担

このツールはAIエージェント本体でも、Gitleaks / Trivyの代替でもありません。

- コードを書く → Codex / Copilot / Cline / Claude Codeなど
- 深いSecret/脆弱性scan → Gitleaks / Trivyなど
- Toolchainを固定する → Dev Containers / miseなど
- **AI作業前にRepoの準備状態を横断確認する → codex-workspace-bootstrap**

## セキュリティ方針

- コア監査はローカル
- secret-risk候補の中身を表示しない
- Repo内容をコア監査から外部AIサービスへ送らない
- AI指示ファイルはローカルで解析するが、抽出したコマンドは実行しない
- symlink経由のAI指示/config・project markerは信頼しない
- `init-agents` / 自動fixはsymlinkされた `AGENTS.md` へ書き込まない
- 通常の既存AGENTS.mdを勝手に上書きしない
- PASSは安全性の保証ではない

詳細は [../SECURITY.md](../SECURITY.md) を参照してください。


## AI指示のdriftをCIで止める

```powershell
cwb preflight . --fail-on-integrity
```

GitHub Actionでは `fail_on_integrity: "true"` を指定します。さらに、`NEEDS ATTENTION` を含めて `READY` 以外をCI失敗にしたい場合は `require_ready: "true"` を指定します。

```powershell
cwb preflight . --require-ready
```

## 安全なfix preview

`cwb fix .` はpreviewのみです。`cwb fix . --apply` でも、AGENTS.md新規生成など低リスクな変更だけを適用し、既存の矛盾した指示ファイルは自動書換えしません。

実在公開Repoをread-onlyで確認した評価は [PUBLIC_REPO_EVALUATIONS.md](PUBLIC_REPO_EVALUATIONS.md) を参照してください。これは第三者利用実績の主張ではありません。


## scope-aware lint

- rootのrepository-wide指示と、特定ディレクトリ向けの指示を区別します。
- Codexのnested `AGENTS.md` / `AGENTS.override.md` を検出します。
- Claude Codeのnested `CLAUDE.md` を検出し、配置ディレクトリをscopeとして扱います。
- Gemini CLIのnested `GEMINI.md` を検出し、配置ディレクトリをscopeとして扱います。`.gemini/settings.json` の `context.fileName` で別名や複数名が設定されている場合もその設定を反映します。
- Cursorのnested `.cursor/rules/*.mdc` を検出し、配置ディレクトリと `globs` / `alwaysApply` を考慮します。
- path-specific instructionの `applyTo` / `globs` から静的なscope prefixを推定します。
- repository-wide / nested指示は同一scopeを中心にdrift比較します。path-specific ruleはRepo根拠との個別検証は行いますが、selector全体の意味を安全に保持できないため相互drift比較から除外します。
- path-specific / nested指示しかなくrepository-wide baselineがない場合はREADYにしません。


## 実際のBefore → Afterデモ

説明だけではなく、実際に壊れたAI向け指示を検出する再現デモを用意しています。

```powershell
py examples/first-run-demo/run_demo.py
```

デモでは、一時的なGitリポジトリを自動生成して次を再現します。

- Repo本体はpnpmなのに `AGENTS.md` がnpmを指定している
- `AGENTS.md` が存在しない `lint` scriptを参照している
- 修正前は `NEEDS ATTENTION`
- 修正後は `READY`

期待される出力の要点:

```text
=== BEFORE ===
State: NEEDS ATTENTION
package-manager-mismatch
missing-package-script

=== AFTER ===
State: READY
Findings: none

Demo verification: PASS
```

詳細は [examples/first-run-demo](../examples/first-run-demo) を参照してください。

これは第三者利用実績の主張ではなく、製品の検出能力を再現可能な形で確認するための技術デモです。
