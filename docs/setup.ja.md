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
cd beacon
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
| `GHE_TOKEN` | 任意（非推奨） | — | GitHub / GHE Personal Access Token（`submit_for_review.py` — 1.1.0 で非推奨化） |
| `GHE_REPO` | 任意（非推奨） | — | `owner/repo` 形式（1.1.0 で非推奨化） |
| `GHE_API_BASE` | 任意 | `https://api.github.com` | セルフホスト GHE 用に上書き |
| `SAGE_API_URL` | SAGE モード | — | SAGE Analysis API の URL（Settings タブからも設定可） |
| `BEACON_STORAGE` | 任意 | `local` | ストレージバックエンド: `local` または `gcs` |
| `BEACON_STORAGE_BASE_DIR` | 任意 | `output/` | `local` バックエンドのベースディレクトリ |
| `BEACON_GCS_BUCKET` | GCS モード | — | GCS バケット名（`BEACON_STORAGE=gcs` 時必須） |
| `BEACON_GCS_PREFIX` | 任意 | (空文字) | GCS バケット内のキープレフィックス |
| `TRACE_ROOT_PATH` | 任意 | — | TRACE リポジトリルートの絶対パス（ダッシュボードの Collection タブ有効化） |

`--no-llm` モード使用時は `GCP_PROJECT_ID` は**不要**。

---

## Step 3b: StorageBackend の設定（オプション）

デフォルトでは成果物は `output/` ディレクトリに保存されます（ローカルバックエンド）。
Google Cloud Storage を使用する場合は以下を設定してください:

```bash
# オプション依存パッケージをインストール
uv sync --extra gcs

# 環境変数を設定（または Web ダッシュボードの Settings タブから設定可）
export BEACON_STORAGE=gcs
export BEACON_GCS_BUCKET=my-beacon-artifacts
export BEACON_GCS_PREFIX=prod/   # 任意; デフォルトは空文字
```

成果物のファイル名は `<category>_<YYYYMMDDHHmm>.json` 形式です。
ローカルバックエンドに戻す場合: `export BEACON_STORAGE=local`

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

SAGE Spanner へのロード (`load_assets.py` は `SAGE/cmd/` 配下のため
ディレクトリを切り替えて実行):

```bash
cd ../SAGE && uv run python cmd/load_assets.py --file ../BEACON/output/assets.json
```

---

## SAGE identity_assets.json の生成

コンテキストドキュメントの `Identities and Access` セクションを
`identity_assets.json` (Initiative A) に変換します。各 identity は
`id` / `name` / `role_tags` / `has_access` エッジ (アセットへのアクセス)
を持ち、BEACON 0.13.0 以降は Initiative C Phase 2 のフラグ
`is_high_value_impersonation_target` と自由形式の
`impersonation_risk_factors` list も搬送します。

```bash
# Markdown から生成 (LLM が必要)
uv run python cmd/generate_identity_assets.py --context input/context.md

# JSON から生成 (LLM 不要)
uv run python cmd/generate_identity_assets.py \
  --context input/context.json \
  --no-llm \
  --output output/identity_assets.json
```

TRACE で検証 (`has_access[].asset_id` を `assets.json` とクロス参照) してから
SAGE にロード:

```bash
cd ../TRACE && uv run python cmd/validate_identity_assets.py \
  --identity-assets ../BEACON/output/identity_assets.json \
  --assets          ../BEACON/output/assets.json

cd ../SAGE  && uv run python cmd/load_identity_assets.py \
  --file ../BEACON/output/identity_assets.json
```

コンテキストドキュメントに identity セクションがない場合、CLI は空の artifact
(`identities: []`, `has_access: []`) を出力し、TRACE はそれを受理します。

---

## SAGE user_accounts.json の生成

`User Accounts` セクションを `user_accounts.json` に変換します。各エントリは
`username` と `identity_id` (任意、`identity_assets.json` へのリンク) を持ち、
`account_on_asset` エッジで「どのアカウントがどのアセット上に存在するか」を
表現します (SAGE のクレデンシャルフロー解析に使用)。

```bash
# Markdown から生成 (LLM が必要)
uv run python cmd/generate_user_accounts.py --context input/context.md

# JSON から生成 (LLM 不要)
uv run python cmd/generate_user_accounts.py \
  --context input/context.json \
  --no-llm \
  --output output/user_accounts.json
```

TRACE で検証してから SAGE にロード:

```bash
cd ../TRACE && uv run python cmd/validate_user_accounts.py \
  --user-accounts ../BEACON/output/user_accounts.json \
  --assets        ../BEACON/output/assets.json

cd ../SAGE  && uv run python cmd/load_user_accounts.py \
  --file ../BEACON/output/user_accounts.json
```

---

## CTI レポートからの STIX バンドル生成

> **BEACON 0.9.0 で TRACE に移管済み (`cmd/stix_from_report.py` は
> BEACON 0.10.0 で削除済)。** PDF / URL → STIX 2.1 抽出は姉妹プロジェクト
> [TRACE](../../TRACE/) に移った。後継コマンドは `TRACE/cmd/crawl_single.py`。
> 詳細は `TRACE/docs/setup.ja.md` と `TRACE/docs/beacon_handoff.md` を参照。

---

## 生成後のレビューとエクスポート

1. **バリデーション** — BEACON 0.9.0 で TRACE に移管済 (`BEACON/cmd/validate_pir.py`
   は BEACON 0.10.0 で削除済)。新しい検証はスキーマに加えて
   タクソノミー照合・資産タグ一致・有効期間も確認します:

   ```bash
   cd ../TRACE && uv run python cmd/validate_pir.py --pir pir_output.json
   # assets.json を併せて渡すと asset_weight_rules のタグ整合性も確認可能:
   cd ../TRACE && uv run python cmd/validate_pir.py --pir pir_output.json --assets assets.json
   ```

2. **レビュー** — `pir_output.json` を手動で確認・編集するか、Web ダッシュボードを使用:

   ```bash
   uv run beacon web   # http://localhost:8000 → PIR タブ → レビュー → エクスポート
   ```

3. **レビュー依頼**（任意）— Web ダッシュボードの **Settings** タブで承認ワークフローを管理。
   旧 GHE CLI は非推奨:

   ```bash
   # BEACON 1.1.0 で非推奨 — Web ダッシュボードを使用してください
   uv run python cmd/submit_for_review.py --pir pir_output.json
   ```

4. **SAGE へデプロイ** — 検証済み PIR を SAGE の `PIR_FILE_PATH` にコピーして ETL を実行:

   ```bash
   cp pir_output.json /path/to/sage/config/pir.json
   # その後 SAGE ETL を実行（docs/sage_integration.ja.md 参照）
   ```

---

## 脅威タクソノミーの更新

`schema/threat_taxonomy.json` は MITRE ATT&CK Enterprise と MISP Galaxy から完全に自動生成されます。アップデータを実行してファイル全体を再構築してください:

```bash
# 変更内容をプレビュー（ファイル書き込みなし）
uv run python -m cmd.update_taxonomy --dry-run

# 実際に更新
uv run python -m cmd.update_taxonomy
```

オプション:

- `--mitre-url` / `--misp-url` — 上流 URL を上書き（デフォルトは `_metadata.sources` に記録されている GitHub raw エンドポイント）
- `--mitre-cache` / `--misp-cache` — fetch の代わりにローカルコピーを読む（エアギャップ環境向け）。`_metadata.sources` にはカノニカル URL が引き続き記録される

> JSON への手動編集は次回実行で上書きされます。新しいアクターやタグ語彙が必要な場合は MITRE/MISP 上流へ提出するか、アップデータ本体を拡張してください。JSON を直接編集してはいけません。

---

## Web ダッシュボード

```bash
uv run beacon web   # デフォルト http://localhost:8000
```

ブラウザで `http://localhost:8000` を開く。

ダッシュボードは 5 つのタブで構成されています:

| タブ | 説明 |
|------|------|
| **Dashboard** | パイプラインサマリ: PIR 件数・収集状況・SAGE のチョークポイント |
| **PIR** | PIR 生成、出力レビュー、StorageBackend からの最新成果物自動ロード |
| **Collection** | TRACE の `crawl-single` / `crawl-batch` をブラウザからサブプロセスとして起動（`TRACE_ROOT_PATH` が必要） |
| **Threats** | SAGE API プロキシ: アクター検索・TTP ルックアップ・threat-summary（`SAGE_API_URL` が必要） |
| **Settings** | ストレージモード・SAGE URL・TRACE パスを設定し `.beacon_settings.json` に永続化 |

**PIR タブ** は 2 つのワークフローを提供します:
- **Business Context から生成** — コンテキストドキュメントをアップロードし、LLM モードまたは辞書のみモードを選択
- **既存 PIR JSON の読み込み** — 生成済みの `pir_output.json` をパイプライン再実行なしにレビュー・編集・エクスポート

> **非推奨:** `cmd/submit_for_review.py`（GHE Issue 作成）は BEACON 1.1.0 で非推奨となり、
> 将来のリリースで削除予定です。承認ワークフローには Settings タブを使用してください。

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
