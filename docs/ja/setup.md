# BEACON — セットアップガイド

英語版（正本）: [`docs/setup.md`](../setup.md)

## 前提条件

| 要件 | バージョン | 備考 |
|------|-----------|------|
| Python | 3.12+ | `pyproject.toml` で指定 |
| [uv](https://docs.astral.sh/uv/) | 最新版 | 仮想環境・パッケージ管理 |
| GCP プロジェクト | — | LLM モード時のみ必要 |
| Git | 2.x+ | フックインストール用 |

---

## Step 1: クローンと依存インストール

```bash
git clone https://github.com/sw33t-b1u/beacon.git
cd beacon/BEACON
uv sync --extra dev
```

---

## Step 2: Git フックをインストール

```bash
make setup
```

`git config core.hooksPath .githooks` を実行し、以下を有効化:

- **pre-commit** — コミット前に `make vet lint` を実行
- **pre-push** — プッシュ前に `make check`（フル品質ゲート）を実行

---

## Step 3: 環境変数を設定

```bash
cp .env.example .env
```

`.env` を編集して必要な値を入力:

| 変数名 | 必須 | デフォルト | 説明 |
|--------|------|-----------|------|
| `GCP_PROJECT_ID` | LLM モード | — | GCP プロジェクト ID |
| `VERTEX_LOCATION` | 任意 | `us-central1` | Vertex AI リージョン |
| `BEACON_LLM_SIMPLE` | 任意 | `gemini-2.5-flash-lite` | 軽量タスク用モデル |
| `BEACON_LLM_MEDIUM` | 任意 | `gemini-2.5-flash` | 中程度タスク用モデル |
| `BEACON_LLM_COMPLEX` | 任意 | `gemini-2.5-pro` | 複雑推論用モデル |
| `GHE_TOKEN` | GHE レビュー | — | GitHub / GHE Personal Access Token |
| `GHE_REPO` | GHE レビュー | — | `owner/repo` 形式 |
| `GHE_API_BASE` | 任意 | `https://api.github.com` | セルフホスト GHE 用に上書き |
| `SAGE_API_URL` | SAGE モード | — | SAGE Analysis API の URL |

`--no-llm` モード使用時は `GCP_PROJECT_ID` は**不要**。

---

## Step 4: GCP 認証（LLM モード時のみ）

```bash
gcloud auth application-default login
```

Vertex AI が使用する Application Default Credentials（ADC）を設定する。API キー管理は不要。

---

## Step 5: セットアップ確認

```bash
# ユニットテスト（GCP 不要）
make test

# フル品質ゲート
make check
```

---

## PIR 生成ワークフロー

### Option A: LLM なしモード（JSON 入力、GCP 不要）

すでに `business_context.json` があり、LLM コストを避けたい場合に使用。

```bash
uv run python cmd/generate_pir.py \
  --context tests/fixtures/sample_context_manufacturing.json \
  --no-llm \
  --output pir_output.json \
  --collection-plan collection_plan.md
```

### Option B: LLM モード — Markdown 入力（GCP 必要）

ビジネスコンテキストが Markdown 形式の戦略ドキュメントの場合に使用。
LLM が Markdown を構造化された `BusinessContext` に変換し、PIR 出力を拡充する。

```bash
# GCP_PROJECT_ID を設定し、ADC を構成済みであること（Step 4 参照）
uv run python cmd/generate_pir.py \
  --context your_strategy_doc.md \
  --output pir_output.json \
  --collection-plan collection_plan.md
```

### Option C: LLM モード — JSON 入力

JSON コンテキストファイルがあり、LLM による説明・収集フォーカスの拡充を使いたい場合。

```bash
uv run python cmd/generate_pir.py \
  --context your_context.json \
  --output pir_output.json \
  --collection-plan collection_plan.md
```

---

## 生成後のレビューとエクスポート

1. **バリデーション** — SAGE 互換 PIR スキーマへの準拠を確認:

   ```bash
   uv run python cmd/validate_pir.py --pir pir_output.json
   ```

2. **レビュー** — `pir_output.json` を手動で確認・編集するか、Web UI を使用:

   ```bash
   uv run python cmd/web_app.py --port 8080
   # ブラウザで http://localhost:8080 → コンテキストをアップロード → レビュー → エクスポート
   ```

3. **GHE レビュー依頼**（任意）— アナリストのサインオフ用に GitHub Issue を作成:

   ```bash
   uv run python cmd/submit_for_review.py --pir pir_output.json
   ```

4. **SAGE へデプロイ** — 検証済み PIR を SAGE の `PIR_FILE_PATH` にコピーして ETL を実行:

   ```bash
   cp pir_output.json /path/to/sage/config/pir.json
   # その後 SAGE ETL を実行（docs/ja/sage_integration.md 参照）
   ```

---

## 脅威タクソノミーの更新

`schema/threat_taxonomy.json` は、業種・地域・ビジネストリガーを脅威アクタータグに対応付けるファイルです。更新方法は2つあります。

**自動更新** — MITRE ATT&CK STIX バンドルから `mitre_groups` と `priority_ttps` を同期:

```bash
# 変更内容をプレビュー（ファイル書き込みなし）
uv run python -m cmd.update_taxonomy --dry-run

# 実際に更新
uv run python -m cmd.update_taxonomy
```

**手動更新** — 以下の項目は `schema/threat_taxonomy.json` を直接編集:
- 新しいアクターカテゴリや国の追加
- `target_industries` / `target_geographies` の調整
- `geography_threat_map`、`industry_threat_map`、`business_trigger_map` の更新

> 自動更新は手動管理セクションを変更しません。MITRE のグループ名や TTP ID を最新化するために、定期的（例: 四半期ごと）に実行することを推奨します。

---

## Web UI（オプション）

```bash
uv run python cmd/web_app.py --port 8080
```

ブラウザで `http://localhost:8080` を開く。

---

## セキュリティスキャン

```bash
make audit
```

`pip-audit` で依存パッケージの既知脆弱性を確認。`make check` に含まれる。

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| `GCP_PROJECT_ID not set` エラー | GCP 未設定で LLM モード使用 | `--no-llm` を使うか `GCP_PROJECT_ID` を設定 |
| `pip-audit` で検出あり | 脆弱な依存パッケージ | `pyproject.toml` でバージョンを更新 |
| フックが動作しない | `make setup` 未実行 | BEACON ディレクトリで `make setup` を実行 |
