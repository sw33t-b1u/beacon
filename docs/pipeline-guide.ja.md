# CTI パイプライン運用ガイド

エンドツーエンドのワークフロー: BEACON → TRACE → SAGE

## データフロー

```
context.md ──→ BEACON ──→ TRACE ──→ SAGE
  (入力)       (PIR策定)   (収集+検証)   (分析+評価)
```

---

## Phase 1: BEACON — PIR + アセット

BEACON はビジネスコンテキストドキュメントを PIR（優先情報要件）と SAGE 用アセットバンドルに変換する。
業種・地域マッチング、オプションの Gemini LLM 拡張、SAGE アクタートリアージ IR-boost を使って
脅威の関連度をスコアリングする。

主要コマンド:

- `beacon pir-generate` — PIR + 収集計画 + 推奨ソース一覧を生成
- `beacon assets-generate` — SAGE 互換の assets.json を生成
- `beacon identity-generate` — identity_assets.json を生成
- `beacon accounts-generate` — user_accounts.json を生成
- `beacon web` — 5 タブダッシュボード (http://localhost:8000)

→ 詳細: [BEACON docs/usage.ja.md](usage.ja.md)

---

## Phase 2: TRACE — 収集 + 検証

TRACE は BEACON の出力成果物を検証し、URL や PDF から外部 CTI レポートを収集する。
PIR 連動の L2 relevance gate でコンテンツをフィルタリングしてから、LLM 駆動の
IoC インデックス付き STIX 2.1 バンドルを生成する。

主要コマンド:

- `trace validate-all` — 収集前に PIR + アセットを検証
- `trace crawl-single` — PIR ゲート付きで単一 URL または PDF をクロール
- `trace crawl-batch` — BEACON 生成のソース一覧を一括クロール
- `trace validate-stix` — 収集済み STIX バンドルを検証
- `trace enrich-bundle` — バンドルに PIR タクソノミータグを付与
- `trace search-iocs` — crawl-state IoC インデックスを検索

→ 詳細: [TRACE docs/usage.md](https://github.com/sw33t-b1u/trace/blob/main/docs/usage.md)

---

## Phase 3: SAGE — 分析

SAGE は BEACON のアセットバンドルと TRACE の STIX バンドルを Spanner Graph に取り込み、
FollowedBy 遷移 weight を計算し、PIR ベースの criticality 調整を適用する。
攻撃パスクエリと脅威サマリのための Analysis API を提供する。

主要コマンド:

- `sage init-schema` — Spanner Graph スキーマの初期化（初回のみ）
- `sage load-assets` — BEACON アセットバンドルのロード
- `sage run-etl` — STIX バンドルを Spanner Graph に取り込む
- `sage serve-api` — Analysis API を起動（デフォルトポート 8080）
- `sage visualize-graph` — インタラクティブ HTML グラフを生成
- `sage incident-register` — IR フィードバックを登録（Diamond Model）

→ 詳細: [SAGE docs/usage.md](https://github.com/sw33t-b1u/sage/blob/main/docs/usage.md)

---

## フィードバックループ

次回以降の BEACON 実行で `beacon pir-generate --use-sage` を指定すると、SAGE に蓄積された
観測データ（インシデント履歴・アクター件数）がアクタートリアージの Intent スコア（`ir_observed`）に
反映され、PIR の精度がサイクルごとに向上する。

→ IR フィードバックループの計算式: [SAGE ir-feedback-flow.md](https://github.com/sw33t-b1u/sage/blob/main/docs/ir-feedback-flow.md)

---

## 環境変数（クイックリファレンス）

### BEACON

| 変数 | デフォルト | 用途 |
|---|---|---|
| `GCP_PROJECT_ID` | (なし) | Vertex AI プロジェクト ID |
| `BEACON_LLM_SIMPLE` | `gemini-2.5-flash-lite` | 単純な抽出タスク用モデル |
| `BEACON_LLM_MEDIUM` | `gemini-2.5-flash` | 中程度の分析用モデル |
| `BEACON_LLM_COMPLEX` | `gemini-2.5-pro` | 複雑な推論（PIR 生成）用モデル |
| `SAGE_API_URL` | (なし) | SAGE API ベース URL（`--use-sage` 有効化） |
| `BEACON_IR_LOOKBACK_DAYS` | `365` | IR boost ルックバックウィンドウ（日数） |
| `BEACON_STORAGE` | `local` | ストレージバックエンド: `local` または `gcs` |
| `BEACON_STORAGE_BASE_DIR` | `output/` | `local` バックエンドのベースディレクトリ |
| `BEACON_STORAGE_BUCKET` | (なし) | GCS バケット名（`gcs` バックエンドで必須） |
| `BEACON_STORAGE_PREFIX` | (空) | GCS バケット内のキープレフィックス |
| `TRACE_ROOT_PATH` | (なし) | TRACE リポジトリルートの絶対パス（Collection タブ有効化） |

### TRACE

| 変数 | デフォルト | 用途 |
|---|---|---|
| `GCP_PROJECT_ID` | (なし) | Vertex AI プロジェクト ID |
| `TRACE_LLM_SIMPLE` | `gemini-2.5-flash-lite` | relevance scoring 用モデル |
| `TRACE_LLM_MEDIUM` | `gemini-2.5-flash` | STIX 抽出用モデル |
| `TRACE_RELEVANCE_THRESHOLD` | `0.5` | L2 PIR relevance gate しきい値（0.0–1.0） |
| `TRACE_CRAWL_CONCURRENCY` | `4` | 並列クロールワーカー数 |
| `TRACE_FEED_MAX_ENTRIES` | `50` | RSS フィードあたりの最大エントリ数 |
| `TRACE_STORAGE` | `local` | ストレージバックエンド: `local` または `gcs` |
| `TRACE_STORAGE_BASE_DIR` | `output/` | `local` バックエンドのベースディレクトリ |
| `TRACE_STORAGE_BUCKET` | (なし) | GCS バケット名（`gcs` バックエンドで必須） |
| `TRACE_STORAGE_PREFIX` | (空) | GCS バケット内のキープレフィックス |

### SAGE

| 変数 | デフォルト | 用途 |
|---|---|---|
| `GCP_PROJECT_ID` | (なし) | Spanner プロジェクト ID |
| `SPANNER_INSTANCE` | (必須) | Spanner インスタンス ID |
| `SPANNER_DB` | (必須) | Spanner データベース ID |
| `SAGE_API_AUTH_TOKEN` | (なし) | API 認証用 Bearer トークン; 未設定時 POST は 503 を返す |
| `PIR_FILE_PATH` | `/config/pir.json` | BEACON の pir_output.json へのパス（ETL の relevance filtering に使用） |
| `SAGE_STORAGE` | `local` | ストレージバックエンド: `local` または `gcs` |
| `SAGE_STORAGE_BASE_DIR` | `output` | ローカルストレージのベースディレクトリ（TRACE/BEACON と共有） |
| `SAGE_STORAGE_BUCKET` | (なし) | GCS バケット名（`SAGE_STORAGE=gcs` 時に必須） |
| `SAGE_STORAGE_PREFIX` | (なし) | GCS オブジェクトキーのプレフィックス（任意） |

---

## コマンドチートシート

```bash
# --- Phase 1: BEACON ---
uv run beacon pir-generate --context input/context.md
uv run beacon assets-generate --context input/context.md
uv run beacon identity-generate --context input/context.md
uv run beacon accounts-generate --context input/context.md
uv run beacon web

# --- Phase 2: TRACE ---
uv run trace validate-all --pir ../BEACON/output/pir_output.json --it-assets ../BEACON/output/assets.json
uv run trace crawl-single --input <URL> --pir ../BEACON/output/pir_output.json
uv run trace crawl-batch --sources input/sources.yaml --pir ../BEACON/output/pir_output.json
uv run trace validate-stix --bundle output/stix/*.json
uv run trace enrich-bundle --input output/stix/bundle.json --output output/stix/bundle_enriched.json
uv run trace search-iocs --ioc <indicator>

# --- Phase 3: SAGE ---
uv run sage init-schema
uv run sage load-assets
uv run sage run-etl
uv run sage serve-api --port 8080
uv run sage visualize-graph
uv run sage incident-register
```
