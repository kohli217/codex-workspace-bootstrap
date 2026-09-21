# codex-workspace-bootstrap 日本語ガイド

Windows上の既存リポジトリを、Codexで扱いやすい状態に診断・初期化するためのCLIです。

> コミュニティ運営のプロジェクトです。OpenAI公式製品ではなく、OpenAIとの提携・所属を示すものではありません。

## できること

- Git / Python / Node.js / npm / PowerShell / WSL / Codex の利用可否を確認
- README / LICENSE / .gitignore / AGENTS.md / 主要マニフェストを確認
- .env・秘密鍵・credential系の「危険になりやすいファイル名」を検出
- Gitが使える場合は、危険候補が追跡済みか・ignore済みかを区別
- Python / Node.js / 混在プロジェクト向けに `AGENTS.md` を生成
- JSON形式で監査結果を保存
- `--strict` でCIのブロッキング判定に利用
- Windows / Ubuntu のGitHub Actionsで自動テスト

## 30秒で試す

公開済みv0.3.0のwheelを固定してインストールします。

```powershell
py -m pip install "https://github.com/kohli217/codex-workspace-bootstrap/releases/download/v0.3.0/codex_workspace_bootstrap-0.3.0-py3-none-any.whl"
```

監査:

```powershell
codex-workspace-bootstrap audit .
```

Codex向けAGENTS.md生成:

```powershell
codex-workspace-bootstrap init-agents .
```

生成する検証コマンドは、pyproject.toml、pytest設定、package.jsonのscript名、READMEに明記されたコマンドを照合します。根拠が弱い候補は確定コマンドと分けてレビュー対象として表示します。

バージョン確認:

```powershell
codex-workspace-bootstrap --version
```

より詳しい例は [EXAMPLES.md](EXAMPLES.md) を参照してください。

## GitHub Actionsから使う

```yaml
- uses: actions/checkout@v7
- uses: actions/setup-python@v7
  with:
    python-version: "3.13"
- uses: kohli217/codex-workspace-bootstrap@v0.3.0
  with:
    path: .
    strict: "true"
```

詳しくは [GITHUB_ACTION.md](GITHUB_ACTION.md) を参照してください。

## CIで使う

```powershell
codex-workspace-bootstrap audit . --strict
```

追跡済みの `.env` や秘密鍵系ファイル名など、明確に危険度が高い検出をブロッキング扱いできます。

## SARIF / GitHub Code Scanning

```powershell
codex-workspace-bootstrap audit . --sarif codex-workspace-bootstrap.sarif
```

ブロッキング項目はSARIFの `error`、通常の警告は `warning` として出力します。GitHub Code Scanningとの連携例は [SARIF.md](SARIF.md) を参照してください。

## JSONレポート

```powershell
codex-workspace-bootstrap audit . --json audit-report.json
```

## セキュリティ上の考え方

このツールは、秘密情報候補ファイルの**中身を読んだり表示したりしません**。コア監査処理はリポジトリ内容を外部サービスへ送信しません。

ただし、監査がPASSでも安全性を保証するものではありません。公開・マージ前にはテスト結果と差分を人間が確認してください。

## Codexと一緒に使う流れ

1. `audit` で現状確認
2. 警告・ブロッキング項目を確認
3. 必要なら `init-agents` で指示ファイル生成
4. CodexにIssue単位の作業を依頼
5. テストとauditを再実行
6. `git diff` を確認
7. CI成功後にマージ・リリース

## 開発・コントリビュート

[CONTRIBUTING.md](../CONTRIBUTING.md) と [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) を参照してください。

## ライセンス

MIT License
