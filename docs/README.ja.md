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
- pyproject.toml / package.json などのproject manifest
- Git / Python / Node.js / npm / PowerShell / WSL / Codex
- AGENTS.md
- GitHub Copilot repository instructions
- Cline / Claude Code / Gemini CLI / Continue / Cursor系の指示ファイル
- .env / private-key系などsecret-riskになりやすいファイル名
- Git追跡済み / ignore済み / untrackedの区別

さらに、packageManager / lockfile / package.json scriptsを根拠に、AI指示間のpackage manager不一致、存在しないscript、test/lint/build系コマンドの食い違いを保守的に検出します。ネストされた `AGENTS.md` / `AGENTS.override.md` と、Copilotの `applyTo` やruleの `globs` から適用scopeも判定し、別scopeの指示を無理に矛盾扱いしません。

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
cwb audit . --sarif audit.sarif
```

## AGENTS.md生成

```powershell
cwb init-agents .
```

pyproject.toml、pytest設定、package.jsonのscript名、READMEに書かれた検証コマンドを照合します。根拠が弱いコマンドは確定扱いせず、review-requiredとして分離します。

## GitHub Actions

GitHub Marketplaceの再利用可能Actionとして利用できます。v0.5.0ではpreflight MarkdownレポートがGitHub Actionsの**Job Summary**に表示されます。

```yaml
- uses: actions/checkout@v7
- uses: actions/setup-python@v7
  with:
    python-version: "3.13"
- uses: kohli217/codex-workspace-bootstrap@v0.5.0
  with:
    path: .
    strict: "true"
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
- 既存AGENTS.mdを勝手に上書きしない
- PASSは安全性の保証ではない

詳細は [../SECURITY.md](../SECURITY.md) を参照してください。


## AI指示のdriftをCIで止める

```powershell
cwb preflight . --fail-on-integrity
```

GitHub Actionでは `fail_on_integrity: "true"` を指定します。

## 安全なfix preview

`cwb fix .` はpreviewのみです。`cwb fix . --apply` でも、AGENTS.md新規生成など低リスクな変更だけを適用し、既存の矛盾した指示ファイルは自動書換えしません。

実在公開Repoをread-onlyで確認した評価は [PUBLIC_REPO_EVALUATIONS.md](PUBLIC_REPO_EVALUATIONS.md) を参照してください。これは第三者利用実績の主張ではありません。


## scope-aware lint

- rootのrepository-wide指示と、特定ディレクトリ向けの指示を区別します。
- Codexのnested `AGENTS.md` / `AGENTS.override.md` を検出します。
- path-specific instructionの `applyTo` / `globs` から静的なscope prefixを推定します。
- 同一scopeの指示同士を中心にdrift比較します。
- path-specific / nested指示しかなくrepository-wide baselineがない場合はREADYにしません。
