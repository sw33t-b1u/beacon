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

# LLM なしで PIR 生成（GCP 不要）
uv run python cmd/generate_pir.py \
  --context tests/fixtures/sample_context_manufacturing.json \
  --no-llm \
  --output /tmp/pir_output.json

uv run python cmd/validate_pir.py --pir /tmp/pir_output.json
```

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
