# BEACON — セットアップガイド

英語版（正本）: [`docs/setup.md`](setup.md)  
Cloud Run デプロイ: [`docs/deploy.ja.md`](deploy.ja.md)

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
| `BEACON_LLM_SIMPLE` | 任意 | `gemini-2.5-flash` | 軽量タスク用モデル |
| `BEACON_LLM_MEDIUM` | 任意 | `gemini-2.5-flash` | 中程度タスク用モデル |
| `BEACON_LLM_COMPLEX` | 任意 | `gemini-2.5-pro` | 複雑推論用モデル |
| `GHE_API_BASE` | 任意 | `https://api.github.com` | セルフホスト GHE 用に上書き |
| `SAGE_API_URL` | SAGE モード | — | SAGE Analysis API の URL（Settings タブからも設定可） |
| `BEACON_STORAGE` | 任意 | `local` | ストレージバックエンド: `local` または `gcs` |
| `BEACON_STORAGE_BASE_DIR` | 任意 | `output/` | `local` バックエンドのベースディレクトリ |
| `BEACON_STORAGE_BUCKET` | GCS モード | — | GCS バケット名（`BEACON_STORAGE=gcs` 時必須） |
| `BEACON_STORAGE_PREFIX` | 任意 | (空文字) | GCS バケット内のキープレフィックス |
| `TRACE_ROOT_PATH` | 任意 | — | TRACE リポジトリルートの絶対パス（ダッシュボードの Collection タブ有効化） |

JSON 入力による生成（Option A）では LLM 呼び出しをスキップするため `GCP_PROJECT_ID` は**不要**。

> **`VERTEX_LOCATION` はデプロイ時に再利用される。** `docs/deploy.ja.md` はこの値から
> gcloud Cloud Run の `REGION` を導出する（`REGION=${VERTEX_LOCATION:-us-central1}`）。
> そのためリージョンはここで一度設定すれば Vertex AI とデプロイコマンドの両方に流れる。
> `REGION` 自体はデプロイ時のシェル変数のみ（**シェルのみ**）であり、BEACON の Python
> コードからは読み込まれない。

---

## Step 3b: StorageBackend の設定（オプション）

デフォルトでは成果物は `output/` ディレクトリに保存されます（ローカルバックエンド）。
Google Cloud Storage を使用する場合は以下を設定してください:

```bash
# 環境変数を設定（または Web ダッシュボードの Settings タブから設定可）
export BEACON_STORAGE=gcs
export BEACON_STORAGE_BUCKET=my-beacon-artifacts
export BEACON_STORAGE_PREFIX=prod/   # 任意; デフォルトは空文字
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

戦略ドキュメントを `input/` ディレクトリに配置してください（テンプレートは [`schema/context_template.ja.md`](../schema/context_template.ja.md) を参照）。`input/` と `output/` ディレクトリは gitignore 対象です — 機密データを含むためコミットしないでください。

`--context` は必須引数です。パスを明示的に指定するため、ファイル名は自由に決められます（例: `input/acme.md`、`input/context_2026Q2.md`）。

### Option A: LLM なしモード（JSON 入力、GCP 不要）

すでに `business_context.json` があり、LLM コストを避けたい場合に使用。

```bash
uv run beacon pir-generate \
  --context tests/fixtures/sample_context_manufacturing.json \
  --output output/
```

### Option B: LLM モード — Markdown 入力（GCP 必要）

```bash
# GCP_PROJECT_ID を設定し、ADC を構成済みであること（Step 4 参照）
uv run beacon pir-generate \
  --context input/acme.md \
  --output output/
```

中間生成物 `BusinessContext` JSON を確認・再利用したい場合は `--save-context` を追加:

```bash
uv run beacon pir-generate \
  --context input/acme.md \
  --save-context output/business_context.json
# 出力: output/pir_output.json, output/collection_plan.md, output/business_context.json
```

### 動作モード — それぞれの存在理由

BEACON には複数の独立した「依存を減らす」モードがある。これらは別々の制御で
あり、混同しないこと。下表は各モードの名称・選択方法・存在理由を示す。

| モード | 選択方法 | 動作 | 存在理由 |
|--------|----------|------|----------|
| **LLM なしモード**（Option A） | `--context <business_context.json>`（Markdown ではなく JSON 入力を指定） | すべての LLM/Vertex AI 呼び出しをスキップし、構造化済みコンテキストを直接消費 | すでに `business_context.json` がある場合に LLM/GCP コストを回避し完全にオフラインで実行 |
| **`--no-sage`** | `beacon pir-generate` の `--no-sage` フラグ | actor-triage の IR-boost SAGE 呼び出しをスキップし `data_quality.ir_boost_skipped` を設定 | `sage-api` が利用不可、または SAGE なしで決定的な実行をしたい場合に SAGE 非依存で生成 |
| **`sage_offline`**（ダッシュボード） | 自動 — ユーザートグルではない | SAGE Analysis API に到達できないときにダッシュボードが示す degraded（縮退）状態 | `SAGE_API_URL` 未設定または `sage-api` 停止時にもダッシュボードを使用可能に保つ |
| **MISP キャッシュ** | 唯一のモード — `beacon misp-cache-refresh` で更新 | 脅威タクソノミー/ギャラクシーデータをローカルキャッシュファイルから読み込む。ライブ MISP 取り込み経路は BEACON 4.0.0 で削除された | 通常の air-gapped/sandbox/コスト無料の経路。生成時にネットワーク依存がない |

用語は意図的に区別する:

- **LLM なし** は *LLM*（Vertex AI）に関する制御: Gemini 呼び出しをスキップする
  JSON 入力経路。SAGE や MISP については何も言わない。
- **`--no-sage`** は *SAGE actor-triage 呼び出し* のみに関する制御。LLM と MISP
  には影響しない。
- **`sage_offline`** は *ダッシュボードの表示状態* であり、自動フォールバック —
  生成フラグではない。
- **MISP キャッシュ** は *脅威タクソノミーデータの取得元* に関する制御。BEACON は
  **キャッシュ専用**である: パイプラインは MISP ギャラクシーデータをローカルキャッシュ
  （`beacon misp-cache-refresh` で更新）からのみ読み込む。ライブ MISP 取り込み経路と
  `pymisp` / `beacon[misp]` オプション extra は **BEACON 4.0.0 で削除された** —
  選択できるライブ MISP モードは存在しない。

---

## テスト

外部サービスは不要です — MISP はモック済み、SAGE はオプションです。

### テストの実行

```bash
# フル品質ゲート（lint + test + audit）
make check

# テストのみ
make test

# uv から直接実行
uv run pytest

# 詳細出力
uv run pytest -v

# 特定のテストファイルを実行
uv run pytest tests/test_element_extractor.py

# 特定のテストクラスまたはメソッドを実行
uv run pytest tests/test_element_extractor.py::TestTriggerDetection
uv run pytest tests/test_element_extractor.py::TestTriggerDetection::test_cloud_dependency
```

### テストフィクスチャ

サンプル入力ファイルは `tests/fixtures/` に格納されています:

```
tests/fixtures/
├── sample_context.json      # ユニットテスト用の最小 BusinessContext
├── sample_context.md        # Markdown 形式のビジネスコンテキスト例
└── ...                      # シナリオ別フィクスチャ
```

テストでフィクスチャを使用するには、標準の `pytest` フィクスチャ機構か直接読み込みを使用します:

```python
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

def test_something():
    ctx = json.loads((FIXTURES / "sample_context.json").read_text())
    ...
```

### 外部サービス不要

| サービス | テスト時の動作 |
|---------|--------------|
| MISP | 呼び出しなし — 脅威タクソノミーデータはすべて `schema/threat_taxonomy.json` から読み込む |
| SAGE | オプション — 実際の API 呼び出しを避けるには `_StubSageClient` を使用 |
| Vertex AI / Gemini | 呼び出しなし — クライアントをモック |
| GCS | 呼び出しなし — テストではストレージが `local` にデフォルト設定 |

### よく使うテストパターン

**SAGE クライアントのスタブ:**

```python
from beacon.sage.client import _StubSageClient

client = _StubSageClient()
# 空のアクターリストを返す；スコアリングロジックのユニットテストに最適
```

**Web アプリのセッションフィクスチャ:**

FastAPI Web アプリのテストは `httpx.AsyncClient` と `ASGITransport` を使用します:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from beacon.web.app import app

@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
```

**LLM 無効化パイプラインのテスト:**

パイプラインオブジェクト構築時に `use_llm=False` を渡します。LLM 呼び出しなしでテストスイートを実行するには:

```bash
uv run pytest
```

### Lint

```bash
make vet      # ruff check（高速）
make lint     # ruff format --check
make format   # ruff format + fix（自動修正）
```

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
| `GCP_PROJECT_ID not set` エラー | GCP 未設定で LLM モード使用 | JSON 入力（Option A）を使うか `GCP_PROJECT_ID` を設定 |
| `pip-audit` で検出あり | 脆弱な依存パッケージ | `pyproject.toml` でバージョンを更新 |
| フックが動作しない | `make setup` 未実行 | BEACON ディレクトリで `make setup` を実行 |
