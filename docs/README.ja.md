# codex-workspace-bootstrap 日本語ガイド

**AIコーディングエージェントにリポジトリを触らせる前のpreflightツール**です。

Windows-first、ローカル実行中心、CI対応。Codexだけでなく、Copilot / Cline / Claude Code / Gemini CLI / Continue / Cursor系の指示ファイルも横断して検出します。

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

Secret候補のファイル内容は表示しません。

## 主なコマンド

```powershell
cwb preflight .
cwb doctor .
cwb audit .
cwb init-agents .
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

GitHub Marketplaceの再利用可能Actionとして利用できます。v0.4.0ではpreflight MarkdownレポートがGitHub Actionsの**Job Summary**に表示されます。

```yaml
- uses: actions/checkout@v7
- uses: actions/setup-python@v7
  with:
    python-version: "3.13"
- uses: kohli217/codex-workspace-bootstrap@v0.4.0
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
