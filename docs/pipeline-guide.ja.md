# CTI パイプライン運用ガイド

BEACON・TRACE・SAGE を組み合わせたエンドツーエンドのワークフロー ——
ビジネスコンテキストからアクショナブルな脅威インテリジェンスまで。

```
context.md ──→ BEACON ──→ TRACE ──→ SAGE
  (入力)       (PIR策定)   (収集+検証)   (分析+評価)
```

---

## 前提条件

| 要件 | 備考 |
|---|---|
| Python ≥ 3.12 | 3 プロジェクト共通 |
| `uv` | パッケージマネージャ; 各リポジトリで `uv sync` を実行 |
| GCP Project (Vertex AI) | 環境変数 `GCP_PROJECT_ID`; BEACON + TRACE の LLM 呼び出しに使用 |
| GCP Spanner インスタンス | SAGE ストレージ; `SPANNER_INSTANCE` + `SPANNER_DB` を設定 |
| `beacon` / `trace` / `sage` CLI | 各リポジトリの `uv sync` でインストールされる |

---

## Phase 1: BEACON — PIR 策定 + 情報収集方針

### 1.1 ビジネスコンテキストドキュメントの準備

`input/context.md` を `docs/context_template.ja.md` のフォーマットに従って作成する。
`input/context.md` は `.gitignore` 対象であり、リポジトリにはコミットされない。

| セクション | PIR 生成への影響 |
|---|---|
| 組織概要（業種・地域・規模） | 業界別脅威マッチング + `geopolitical_exposure` trigger |
| 戦略目標（M&A・IPO・提携） | `m_and_a` / `ipo_or_listing` trigger |
| プロジェクト（AI/ML 利用の有無） | `ai_adoption_exposure` trigger |
| IT 資産（サーバ・NW・クラウド） | SAGE 用アセットバンドル + 脆弱性マッチング |
| 事業継続計画（BCP/DR テスト頻度） | `ransomware_resilience_gap` trigger |
| ID 管理（MFA 率・PIM/PAM） | `identity_credential_exposure` trigger |
| 規制要件（FISC・PCI-DSS 等） | `regulatory_change` trigger |

### 1.2 PIR + 情報収集計画 + 推奨ソース一覧を一括生成

```bash
cd BEACON/

uv run beacon pir-generate \
  --context input/context.md \
  --output-dir output/
```

3 つの成果物が生成され、レビュー用 Web UI が自動起動する:

| 出力ファイル | 目的 |
|---|---|
| `output/pir_output.json` | PIR ドキュメント（CU-GIR ID 付き、schema_version 1.0.0、wrapped envelope 形式） |
| `output/collection_plan.md` | PIR ごとの収集指針: 頻度・担当ロール・推奨アクション |
| `output/sources_candidate.yaml` | 推奨 CTI ソース一覧（tier / 地域 / 業種 / ATT&CK Group ID 注釈付き） |

Web UI (`http://localhost:<port>/`) で全成果物を一覧確認できる。
ヘッドレス実行時は `--no-web` で抑止可能。

**主要オプション:**

| フラグ | 効果 |
|---|---|
| `--use-sage` | SAGE の観測データを risk scoring に反映（`SAGE_API_URL` が必要） |
| `--no-sage` | actor triage の IR-boost SAGE 呼び出しをスキップ |
| `--save-context <path>` | パース済み BusinessContext を JSON で出力（デバッグ用） |

### 1.3 アセットバンドルの生成（SAGE 投入用）

```bash
uv run beacon assets-generate --context input/context.md
uv run beacon identity-generate --context input/context.md
uv run beacon accounts-generate --context input/context.md
```

成果物は設定済み StorageBackend（下記参照）に保存される。

### 1.4 StorageBackend — 成果物の永続化

BEACON が生成するすべての成果物は `output/` への直接書き込みではなく、
プラガブルな **StorageBackend** を経由して保存される。バックエンドは
`BEACON_STORAGE` 環境変数で選択する。

```
BEACON パイプライン
      │
      ├─── StorageBackend.save(category="pir",   filename="pir_202506011430.json")
      ├─── StorageBackend.save(category="assets", filename="assets_202506011430.json")
      └─── StorageBackend.save(category="plans",  filename="plans_202506011430.json")
```

**ローカルバックエンド（デフォルト）:**

```bash
export BEACON_STORAGE=local
export BEACON_STORAGE_BASE_DIR=output/   # 任意（デフォルトは output/）
uv run beacon pir-generate --context input/context.md
```

**GCS バックエンド:**

```bash
# 事前に: uv sync --extra gcs
export BEACON_STORAGE=gcs
export BEACON_GCS_BUCKET=my-beacon-artifacts
export BEACON_GCS_PREFIX=prod/          # 任意; デフォルトは "beacon/"
uv run beacon pir-generate --context input/context.md
```

ファイル名形式: `<category>_<YYYYMMDDHHmm>.json`（例: `pir_202506011430.json`）。
Dashboard・PIR タブは各カテゴリの最新ファイルを自動ロードする。

### 1.5 Web ダッシュボード

ダッシュボードを起動してパイプライン状況を一元管理できる:

```bash
uv run beacon web   # デフォルト http://localhost:8000
```

| タブ | できること |
|------|-----------|
| **Dashboard** | PIR 件数・収集状況・SAGE から取得したチョークポイントを確認 |
| **PIR** | PIR 生成の実行、生成結果レビュー、StorageBackend からの過去実行読み込み |
| **Collection** | TRACE の `crawl-single` / `crawl-batch` をブラウザからサブプロセスとして起動 |
| **Threats** | SAGE API プロキシ経由でアクター検索・TTP ルックアップ・`/threat-summary` 取得 |
| **Settings** | ストレージモード・SAGE URL・TRACE パスを設定し `.beacon_settings.json` に永続化 |

設定優先順位: **環境変数**（最高）> **`.beacon_settings.json`** > **組み込みデフォルト**

> Collection タブを TRACE に接続するには、`TRACE_ROOT_PATH` に TRACE リポジトリルートの
> 絶対パス（例: `/path/to/TRACE`）を設定すること。

---

## Phase 2: TRACE — 脅威情報の収集 + 検証

### 2.1 BEACON 出力の検証

```bash
cd TRACE/

uv run trace validate-all \
  --pir ../BEACON/output/pir_output.json \
  --it-assets ../BEACON/output/assets.json
```

PIR と assets のバリデーターを一括実行し、Markdown レポートを出力する。
問題が検出された場合は修正してから次のステップへ。

identity と accounts の検証は個別コマンドを使用:

```bash
uv run trace validate-identity --identity-assets ../BEACON/output/identity_assets.json \
                        --it-assets ../BEACON/output/assets.json
uv run trace validate-accounts --user-accounts ../BEACON/output/user_accounts.json \
                        --it-assets ../BEACON/output/assets.json
```

### 2.2 脅威レポートの収集（PIR 連動）

**個別 URL / PDF:**

```bash
uv run trace crawl-single \
  --input https://www.jpcert.or.jp/at/2025/at250001.html \
  --pir ../BEACON/output/pir_output.json
```

L2 PIR relevance gate が自動適用される。PIR との関連度がしきい値未満の記事は
スキップされ、関連度が高い記事のみ STIX 2.1 バンドル + LLM 抽出 IoC として出力。

デフォルトでは **StorageBackend** にバンドルが書き込まれる
（`LocalStorage` の場合: `output/stix/stix_bundle_<YYYYMMDDHHmm>.json`）。
明示パスに書き出したい場合は `--output <path>` を指定すると StorageBackend をバイパスする。

**バッチ収集（推奨ソース一括）:**

```bash
# BEACON が生成した sources_candidate.yaml を input/ にコピー
cp ../BEACON/output/sources_candidate.yaml input/sources.yaml

uv run trace crawl-batch \
  --sources input/sources.yaml \
  --pir ../BEACON/output/pir_output.json
```

`sources_candidate.yaml` に列挙された各ソース URL をクロールし、
PIR relevance gate を通過したもののみ STIX バンドル化する。
各バンドルは StorageBackend の `stix/` カテゴリに保存される
（デフォルト: `output/stix/stix_bundle_<YYYYMMDDHHmm>.json`）。
明示ディレクトリに書き出す場合は `--output-dir <dir>` を指定する。

#### TRACE StorageBackend 設定

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `TRACE_STORAGE` | `local` | `local` または `gcs` |
| `TRACE_STORAGE_BASE_DIR` | `output/` | `LocalStorage` のルートディレクトリ |
| `TRACE_GCS_BUCKET` | — | `TRACE_STORAGE=gcs` 時に必須 |
| `TRACE_GCS_PREFIX` | `trace/` | GCS バケット内のキープレフィックス |

#### BEACON Collection タブとの連携

BEACON の **Collection** タブは `crawl-batch` をサブプロセスとして起動する。
TRACE は各バンドルを StorageBackend に書き込み、BEACON は `stix/` カテゴリを
スキャンして結果を一覧表示する。

```
BEACON Web UI（Collection タブ）
  └─► サブプロセス: uv run trace crawl-batch --pir pir_output.json
        └─► StorageBackend.write("stix", "stix_bundle_YYYYMMDDHHmm.json", data)
              └─► output/stix/stix_bundle_YYYYMMDDHHmm.json  (LocalStorage)
                  gs://<bucket>/trace/stix/stix_bundle_YYYYMMDDHHmm.json  (GCSStorage)
```

BEACON は自身の StorageBackend（同一ベースディレクトリまたは GCS バケットを参照）
の `stix/` カテゴリからバンドル一覧を読み取る。

### 2.3 収集済み STIX バンドルの検証

```bash
uv run trace validate-stix --bundle output/stix/*.json
```

### 2.4 PIR タグによるエンリッチメント（任意）

```bash
uv run trace enrich-bundle \
  --input output/stix/bundle_xxx.json \
  --output output/stix/bundle_xxx_enriched.json
```

STIX オブジェクトに taxonomy タグを付与し、SAGE での下流フィルタリングを支援。

### 2.5 抽出済み IoC の検索

```bash
uv run trace search-iocs --ioc 203.0.113.42
```

crawl-state IoC インデックスから特定の Indicator 値を検索。

---

## Phase 3: SAGE — 脅威動向の分析 + リスク評価

### 3.1 Spanner Graph の初期化（初回のみ）

```bash
cd SAGE/

uv run sage init-schema
```

### 3.2 BEACON アセットデータのロード

`SAGE_STORAGE_BASE_DIR` が BEACON の出力ディレクトリを指している場合、
`--input` を省略すると StorageBackend の `assets/` カテゴリから最新ファイルを
自動取得する:

```bash
# --input を明示（常に動作）
uv run sage load-assets           --input ../BEACON/output/assets.json
uv run sage load-identity-assets  --input ../BEACON/output/identity_assets.json
uv run sage load-user-accounts    --input ../BEACON/output/user_accounts.json

# --input 省略 — StorageBackend から自動取得（SAGE_STORAGE_BASE_DIR/assets/）
uv run sage load-assets
uv run sage load-identity-assets
uv run sage load-user-accounts
```

### 3.3 STIX バンドルの取り込み（ETL）

**StorageBackend モード（推奨）:** `--input` なしの `run-etl` は、StorageBackend の
`stix/` カテゴリにある**全バンドル**を読み込んで処理する。TRACE が `output/stix/` に
バンドルを書き込む標準パスがこれに該当する:

```bash
export PIR_FILE_PATH=../BEACON/output/pir_output.json

# StorageBackend の stix/ カテゴリから全バンドルを処理
uv run sage run-etl
```

**単一ファイルモード:** 特定のバンドルを処理する場合は `--input` を指定する:

```bash
uv run sage run-etl --input ../TRACE/output/stix/bundle.json
```

ETL パイプラインは STIX 2.1 バンドルをパースし、Spanner Graph のノード・エッジに
マッピングする。`FollowedBy` エッジの weight は kill chain phase 順の
アクター間遷移確率として自動計算され、PIR ベースのアセット criticality 調整も適用。
StorageBackend モードでは全バンドルの統計を集計して単一の Slack 通知を送信する。

### 3.4 Analysis API の起動

```bash
uv run sage serve-api --port 8080
```

### 3.5 脅威インテリジェンスのクエリ

| エンドポイント | メソッド | 用途 |
|---|---|---|
| `/threat-summary?asset=<id>` | GET | アセット単位の脅威サマリ: 関連アクター・攻撃パス・チョークポイント・脆弱性・インシデント |
| `/actor-ttps?actor_id=<id>&since=YYYY-MM-DD&until=YYYY-MM-DD` | GET | アクター別 TTP 一覧（期間指定可） |
| `/actors?name=<query>&limit=20` | GET | アクター名の大小文字を区別しない部分一致検索（最小 2 文字）; `{"actors":[…],"count":N}` を返す |
| `/attack-paths?asset_id=<id>&limit=N` | GET | 多段攻撃パス探索（アクター → アセット） |
| `/choke-points` | GET | 防御優先度 — グラフ全体のチョークポイント計算 |
| `/asset-exposure?since=YYYY-MM-DD` | GET | 外部露出アセットと到達可能な TTP 数（時間ウィンドウ指定） |
| `/similar-incidents?incident_id=<id>` | GET | 類似インシデント検索（TTP Jaccard + 遷移カバレッジ） |
| `/api/incidents` | POST | インシデント直接登録（Diamond Model） |
| `/api/incidents?since=YYYY-MM-DD` | GET | 登録済みインシデントの取得 |
| `/api/annotate` | POST | アクターへのアナリスト注釈の記録 |

**例 — 過去半年の脅威動向確認:**

```bash
# アクター別 TTP（過去 6 ヶ月）
curl "http://localhost:8080/actor-ttps?actor_id=intrusion-set--apt-XX&since=2025-01-01"

# 基幹システムの脅威サマリ
curl "http://localhost:8080/threat-summary?asset=core-banking-001"

# 基幹システムへの攻撃パス（上位 10 件）
curl "http://localhost:8080/attack-paths?asset_id=core-banking-001&limit=10"

# 防御優先度
curl "http://localhost:8080/choke-points"
```

### 3.6 攻撃グラフの可視化

```bash
uv run sage visualize-graph
```

Spanner Graph のノード・エッジを pyvis でインタラクティブな HTML として可視化。

### 3.7 IR フィードバックの登録（任意）

過去のインシデント情報を登録し、次回の PIR 生成に反映する:

```bash
uv run sage incident-register
```

Diamond Model の 4 象限（adversary / capability / infrastructure / victim）を
対話的に入力。kill chain phase と IoC フィールドも指定可能。

---

## フィードバックループ

```
                 ┌──────────────────────────────────────────┐
                 │                                          ▼
BEACON           TRACE              SAGE               BEACON（次回）
pir-generate ──→ crawl-batch ──→  run-etl ──→         pir-generate
  PIR             (PIR gate)      Spanner Graph          --use-sage
  collection      STIX bundles    /threat-summary         │
  sources.yaml                    /actor-ttps             IR boost が
                                  incident-register ──→  Likelihood に
                                                         反映される
```

次回の `beacon pir-generate --use-sage` 実行時に、SAGE に蓄積された観測データが
actor triage の Likelihood スコア（`ir_observed_capability` +
`ir_observed_opportunity`）に反映され、PIR の精度がサイクルごとに向上する。

---

## 環境変数

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
| `BEACON_GCS_BUCKET` | (なし) | GCS バケット名（`gcs` バックエンドで必須） |
| `BEACON_GCS_PREFIX` | `beacon/` | GCS バケット内のキープレフィックス |
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
| `TRACE_GCS_BUCKET` | (なし) | GCS バケット名（`gcs` バックエンドで必須） |
| `TRACE_GCS_PREFIX` | `trace/` | GCS バケット内のキープレフィックス |

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
| `SAGE_GCS_BUCKET` | (なし) | GCS バケット名（`SAGE_STORAGE=gcs` 時に必須） |
| `SAGE_GCS_PREFIX` | (なし) | GCS オブジェクトキーのプレフィックス（任意） |

---

## コマンドチートシート

```bash
# --- Phase 1: BEACON ---
uv run beacon pir-generate --context input/context.md
uv run beacon assets-generate --context input/context.md
uv run beacon identity-generate --context input/context.md
uv run beacon accounts-generate --context input/context.md
uv run beacon web                                           # 5 タブダッシュボード（http://localhost:8000）

# --- Phase 2: TRACE ---
uv run trace validate-all --pir ../BEACON/output/pir_output.json --it-assets ../BEACON/output/assets.json
uv run trace crawl-single --input <URL> --pir ../BEACON/output/pir_output.json
uv run trace crawl-batch --sources input/sources.yaml --pir ../BEACON/output/pir_output.json
uv run trace validate-stix --bundle output/stix/*.json
uv run trace enrich-bundle --input output/stix/bundle.json --output output/stix/bundle_enriched.json
uv run trace search-iocs --ioc <indicator>

# --- Phase 3: SAGE ---
uv run sage init-schema
uv run sage load-assets                                         # StorageBackend 自動取得
uv run sage load-assets --input ../BEACON/output/assets.json   # 明示パス
uv run sage run-etl                                             # StorageBackend: 全 stix/ バンドル
uv run sage run-etl --input ../TRACE/output/stix/bundle.json   # 単一ファイルモード
uv run sage serve-api --port 8080
uv run sage query-attack-paths --asset-id <id>
curl "http://localhost:8080/actors?name=apt&limit=10"           # アクター名検索
uv run sage visualize-graph
uv run sage incident-register
```
