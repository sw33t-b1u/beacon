# BEACON — セットアップガイド

英語版（正本）: [`docs/setup.md`](setup.md)

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

戦略ドキュメントを `input/` ディレクトリに配置してください（テンプレートは [`docs/context_template.ja.md`](context_template.ja.md) を参照）。`input/` と `output/` ディレクトリは gitignore 対象です — 機密データを含むためコミットしないでください。

`--context` は必須引数です。パスを明示的に指定するため、ファイル名は自由に決められます（例: `input/acme.md`、`input/context_2026Q2.md`）。

### Option A: LLM なしモード（JSON 入力、GCP 不要）

すでに `business_context.json` があり、LLM コストを避けたい場合に使用。

```bash
uv run python cmd/generate_pir.py \
  --context tests/fixtures/sample_context_manufacturing.json \
  --no-llm \
  --output output/pir_output.json \
  --collection-plan output/collection_plan.md
```

### Option B: LLM モード — Markdown 入力（GCP 必要）

```bash
# GCP_PROJECT_ID を設定し、ADC を構成済みであること（Step 4 参照）
uv run python cmd/generate_pir.py \
  --context input/acme.md \
  --output output/pir_output.json \
  --collection-plan output/collection_plan.md
```

中間生成物 `BusinessContext` JSON を確認・再利用したい場合は `--save-context` を追加:

```bash
uv run python cmd/generate_pir.py \
  --context input/acme.md \
  --save-context output/business_context.json
# 出力: output/pir_output.json, output/collection_plan.md, output/business_context.json
```

---

## SAGE assets.json の生成

コンテキストドキュメントの `Critical Assets` セクションを SAGE 互換の `assets.json` に変換し、Spanner へのロードに使用します。

```bash
# Markdown から生成（LLM / Vertex AI が必要）
uv run python cmd/generate_assets.py --context input/context.md

# JSON から生成（LLM 不要）
uv run python cmd/generate_assets.py \
  --context input/context.json \
  --no-llm \
  --output output/assets.json
```

生成ファイルは `output/assets.json` に書き出されます。以下のフィールドを手動で補完してください:

| フィールド | 作業内容 |
|-----------|---------|
| `owner` | アセットごとのチームメールアドレスや担当名 |
| `security_controls` | EDR/SIEM/ファイアウォールのエントリを定義 |
| `security_control_ids` | アセットとセキュリティコントロールを紐付け |
| `asset_vulnerabilities` | STIX ETL 実行後に設定 |
| `actor_targets` | STIX ETL 実行後に設定 |

SAGE Spanner へのロード:

```bash
uv run python cmd/load_assets.py --file output/assets.json
```

---

## CTI レポートからの STIX バンドル生成

PDF レポートや Web 記事を STIX 2.1 バンドルに変換して SAGE ETL へ投入できます。

```bash
# PDF から生成
uv run python cmd/stix_from_report.py --input report.pdf

# Web 記事 URL から生成（zsh/bash では ? & = が特殊文字のためシングルクォートで囲む）
uv run python cmd/stix_from_report.py --input 'https://example.com/apt-analysis?id=1'

# 出力先を指定
uv run python cmd/stix_from_report.py --input report.pdf --output output/apt29_bundle.json

# 高精度モデルを使用（遅い: 2〜5分）
uv run python cmd/stix_from_report.py --input report.pdf --task complex

# 長いレポート向けに入力サイズを増やす（デフォルト: 20000文字）
uv run python cmd/stix_from_report.py --input report.pdf --max-chars 30000
```

デフォルト出力先は `output/stix_bundle.json`。SAGE ETL への投入:

```bash
uv run python cmd/run_etl.py --manual-bundle output/stix_bundle.json
```

抽出する STIX タイプ: `intrusion-set`、`attack-pattern`、`malware`、`tool`、
`vulnerability`、`indicator`、`relationship`

> **Note:** `markitdown[pdf]` が必要ですが、標準依存関係に含まれています（`uv sync`）。PDF と Web 記事の両方をクリーンな Markdown に変換し、ナビゲーションやフッターを除去してプロンプトサイズを削減します。

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
   # その後 SAGE ETL を実行（docs/sage_integration.ja.md 参照）
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

**`threat_tag_completion.md` ホワイトリストの更新** — LLM フォールバックパスが有効になると（辞書でマッチ 0 件）、`src/beacon/llm/prompts/threat_tag_completion.md` が LLM の出力グループ名を制約します。このホワイトリストは以下のリファレンスを参考に手動で管理します。

| ソース | 更新対象 |
|--------|---------|
| [MITRE ATT&CK Groups](https://attack.mitre.org/groups/) | 国家支援・犯罪グループの正式名称 |
| [MISP Galaxy threat-actor cluster](https://github.com/MISP/misp-galaxy) | エイリアス、新興アクター |
| [BushidoUK Ransomware Tool Matrix](https://github.com/BushidoUK/Ransomware-Tool-Matrix) | 活動中の RaaS・ランサムウェアグループ名 |

`threat_tag_completion.md` の `## Notable Group Reference` セクションを編集してグループを追加・削除してください。`threat_taxonomy.json` のアクターカテゴリとの整合性を保つこと。

---

## Web UI（オプション）

```bash
uv run python cmd/web_app.py --port 8080
```

ブラウザで `http://localhost:8080` を開く。

Web UI は 2 つのワークフローを提供します。

**Business Context から生成** — `business_context.json` または Markdown 形式の戦略ドキュメントをアップロードし、モードを選択:
- **Dictionary only**（LLM なし / GCP 不要） — 高速な辞書ベース PIR 生成
- **LLM mode**（GCP 必要） — Google Gen AI（Gemini）による説明・根拠・収集フォーカスの拡充。LLM モード選択時は、各タスクレベル（simple / medium / complex）のモデルを UI 上で上書き可能（空白のままにすると `.env` のデフォルト値を使用）

**既存の PIR JSON を読み込む** — 生成済みの `pir_output.json` をアップロードして、パイプラインを再実行せずにレビュー・編集・エクスポートできます。

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
