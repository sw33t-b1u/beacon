# BEACON — 使用ガイド

英語版（正本）: [`docs/usage.md`](usage.md)

このガイドはアナリストおよびオペレーターが BEACON を日常的に使用する際のリファレンスです。
環境構築は [docs/setup.ja.md](setup.ja.md)、Cloud Run デプロイは [docs/deploy.ja.md](deploy.ja.md) を参照。

---

## Web ダッシュボード

ダッシュボードを起動する:

```bash
uv run beacon web          # デフォルト: http://localhost:8000
```

ダッシュボードは 8 つのタブで構成されます:

| タブ | 用途 |
|------|------|
| **Dashboard** | パイプラインサマリ: PIR 件数・収集状況・チョークポイント |
| **PIR** | PIR 生成・出力レビュー・StorageBackend からの過去実行自動ロード |
| **Assets** | `assets_*.json` ドラフトをロードし、org-known フィールド（owner・セキュリティコントロール・CVE マッピング）を補完して StorageBackend に保存 |
| **Identity** | `identity_assets_*.json` ドラフトをロードし、org-known フィールド（description・roles・impersonation リスクフラグ・has_access エッジ）を補完して StorageBackend に保存 |
| **Accounts** | `user_accounts_*.json` ドラフトをロードし、org-known フィールド（表示名・アカウント種別・権限フラグ・account_on_asset エッジ）を補完して StorageBackend に保存 |
| **Collection** | TRACE の `crawl-single` / `crawl-batch` をサブプロセスで実行 |
| **Threats** | SAGE API プロキシ: アクター検索・TTP ルックアップ・脅威サマリ |
| **Settings** | ストレージモード・SAGE URL・TRACE パスを設定。`.beacon_settings.json` に永続化 |

設定の優先順位: **環境変数 > `.beacon_settings.json` > デフォルト値**

---

## CLI コマンド

すべてのコマンドは `uv sync` でインストールされる `beacon` エントリポイントから実行します。

### `beacon pir-generate`

ビジネスコンテキストドキュメントから PIR JSON を生成します。

このコマンドは同じ解析済みコンテキストから 3 つのコンパニオンドラフト成果物も同時に生成します:

| 成果物 | StorageBackend カテゴリ | ファイル名パターン |
|--------|------------------------|-----------------|
| `assets.json` | `assets` | `assets_<YYYYMMDDHHmm>.json` |
| `identity_assets.json` | `assets` | `identity_assets_<YYYYMMDDHHmm>.json` |
| `user_accounts.json` | `assets` | `user_accounts_<YYYYMMDDHHmm>.json` |

`asset_vulnerabilities` と `actor_targets` はドラフトでは空のままです — STIX ETL 実行後または専用の generate コマンドで補完してください。

```bash
beacon pir-generate                    # input/context.md を使用、フル LLM モード
beacon pir-generate --no-llm           # 辞書ベースのみ、Gemini 呼び出しなし
beacon pir-generate --no-sage          # SAGE アクタートリアージ拡張をスキップ
beacon pir-generate --use-sage         # SAGE 拡張を明示的に有効化
beacon pir-generate --save-context     # 構造化 BusinessContext を output/ に保存
```

### `beacon assets-generate`

ビジネスコンテキストから `assets.json` を生成します。

```bash
beacon assets-generate
beacon assets-generate --no-llm
```

### `beacon identity-generate`

`identity_assets.json`（Identity ノード + `has_access` エッジ）を生成します。

```bash
beacon identity-generate
beacon identity-generate --no-llm
```

### `beacon accounts-generate`

`user_accounts.json`（UserAccount ノード + `account_on_asset` エッジ）を生成します。

```bash
beacon accounts-generate
```

### `beacon web`

Web ダッシュボードを起動します。

```bash
beacon web                 # http://localhost:8000
beacon web --no-web        # ドライラン / バリデーションのみ（サーバー起動なし）
```

---

## 主要フラグ

| フラグ | 効果 |
|--------|------|
| `--use-sage` | SAGE アクタートリアージ API 呼び出しを有効化 |
| `--no-sage` | SAGE 呼び出しを無効化（SAGE が利用不可の場合に便利） |
| `--no-llm` | すべての Gemini / Vertex AI 呼び出しをスキップ（辞書のみモード） |
| `--no-web` | Web サーバー起動をスキップ |
| `--save-context` | 解析した `BusinessContext` JSON を `output/` に書き出す |

---

## PIR レビューワークフロー

1. **生成** — `beacon pir-generate` を実行するか、PIR タブの **Generate** をクリック。
2. **レビュー** — PIR タブで各 PIR のスコア内訳（likelihood・impact・intelligence level・アクタータグ）を確認。
3. **承認** — Web ダッシュボードで PIR をレビューして承認します。**Settings** タブで承認ワークフローを設定。
4. **エクスポート** — 承認済み成果物は設定済み StorageBackend（`local` または `gcs`）を経由して保存。
   ファイル名は `<type>_<YYYYMMDDHHmm>.json` 形式（例: `pir_202506011430.json`）。

---

## Assets タブワークフロー

**Assets** タブでは、ブラウザ上で `assets.json` の org-known ドラフトフィールドを補完できます（JSON の手動編集不要）。

### 編集可能なフィールド

| フィールド | assets.json 内の場所 | 説明 |
|------------|---------------------|------|
| `owner` | 各アセット | チーム名またはメールアドレス |
| `security_control_ids` | 各アセット | カンマ区切りのコントロール ID |
| `security_controls` | トップレベルリスト | EDR・SIEM・ファイアウォール等のエントリを定義 |
| `asset_vulnerabilities` | トップレベルリスト | org スキャナーデータ: CVE id → asset_id マッピング |

**`actor_targets` は CTI 由来のフィールドであり、ここでは編集できません。** STIX バンドルの取り込み時に SAGE ETL が自動補完します。

### 手順

1. **生成** — `beacon pir-generate` を実行するか、PIR タブで Generate をクリック。
   StorageBackend の `assets` カテゴリに 3 つのドラフトファイルが書き出されます:
   `assets_<ts>.json`、`identity_assets_<ts>.json`、`user_accounts_<ts>.json`。

2. **ドラフトのロード** — **Assets** タブを開きます。**Stored Assets Drafts** セクションの
   対象 `assets_*.json` の **Load** ボタンをクリック。ドラフトがブラウザセッションに読み込まれます。

3. **org-known フィールドの補完**:
   - 各アセットの **Owner** 列にチーム名またはメールアドレスを入力。
   - 各アセットの **Security Control IDs** にカンマ区切りで ID を入力。
   - **Security Controls** JSON 配列を編集して EDR・SIEM・ファイアウォール等のエントリを定義
     （各エントリに `id`・`name`・`type` が必要）。
   - **Asset Vulnerabilities** JSON 配列に脆弱性スキャナーの出力を貼り付け。
     各エントリは以下を含む必要があります:
     - `vuln_stix_id_ref`: CVE id（形式: `CVE-<year>-<4桁以上の数字>`）
     - `asset_id`: 影響を受けるアセットの ID
     - `remediation_status`（省略可）: `open` | `in_progress` | `resolved`

4. **保存** — **Save to StorageBackend** をクリック。設定済み StorageBackend に
   新しい `assets_<YYYYMMDDHHmm>.json` が書き出されます。

5. **SAGE への読み込み** — `SAGE/` ディレクトリで:

   ```bash
   cd ../SAGE && uv run sage load-assets --file output/assets.json
   ```

   Spanner に存在しない CVE に対しては SAGE がスタブ `Vulnerability` ノードを
   作成します（TRACE の命名と一致する決定論的 uuid5 ID）。同一 CVE を含む STIX バンドルが
   後で取り込まれた場合、SAGE は既存のスタブノードを upsert（エンリッチ）します。

### CVE id バリデーション

`asset_vulnerabilities` の CVE id は `^CVE-\d{4}-\d{4,}$` 形式で検証されます。
不正な形式の id が含まれる場合、保存エンドポイントは HTTP 400 を返します。

---

## よくある操作

### LLM モデルティアの変更

`.env` で `VERTEX_MODEL` を設定するか、実行前にエクスポートします:

```bash
VERTEX_MODEL=gemini-2.0-flash beacon pir-generate
```

使用可能な値は Vertex AI プロジェクトのクォータに依存します。

### 過去の PIR 結果を読み込む

PIR タブには StorageBackend から取得した過去の実行一覧が表示されます。
ドロップダウンから実行を選択すると、再生成せずにレビュービューへ読み込めます。

パスを直接指定することもできます:

```bash
beacon pir-generate --input output/pir_202506011430.json --review-only
```

### GCS ストレージへの切り替え

```bash
export BEACON_STORAGE=gcs
export BEACON_GCS_BUCKET=my-beacon-bucket
beacon pir-generate
```

ストレージ環境変数の完全な一覧は [docs/setup.ja.md](setup.ja.md) を参照。

---

## MISP キャッシュの更新

### 目的

BEACON は [MISP Galaxy](https://github.com/MISP/misp-galaxy) の
脅威アクタークラスター（`cache/misp-threat-actor.json`）のローカルコピーを、
アクターの帰属・標的業界の分類・巧妙さスコアリングのタクソノミーフォールバックとして使用する。
このキャッシュは `MispClient` によって読み込まれ、PIR 生成中に照会される。

キャッシュを最新の状態に保つことで、MISP コミュニティから新たに追加された
アクターや更新されたメタデータが、コード変更なしに BEACON の出力に反映される。

### 更新の実行

```bash
# デフォルト: cache/misp-threat-actor.json に書き込む
beacon misp-cache-refresh

# カスタム出力パスを指定
beacon misp-cache-refresh --output /path/to/misp-threat-actor.json

# ディスクに書き込まずにダウンロードを検証
beacon misp-cache-refresh --dry-run

# すべてのオプション
beacon misp-cache-refresh --help
```

### 推奨 cron エントリ（毎日 03:00 ローカル時間）

```cron
0 3 * * * cd /path/to/beacon && unset ALL_PROXY all_proxy HTTP_PROXY http_proxy HTTPS_PROXY https_proxy FTP_PROXY ftp_proxy RSYNC_PROXY GRPC_PROXY grpc_proxy NO_PROXY no_proxy; export UV_CACHE_DIR=$TMPDIR/uv-cache; beacon misp-cache-refresh >> /var/log/beacon/misp_refresh.log 2>&1
```

cron エントリを有効化する前にログディレクトリを作成すること:

```bash
mkdir -p /var/log/beacon
```

### 失敗時のセマンティクス

本スクリプトは**フェイルセーフ**な設計となっている:

- ダウンロードまたはパースが失敗した場合、**既存のキャッシュはそのまま残る**
  （`tempfile` + `os.replace` によるアトミック書き込みにより、部分的な書き込みは発生しない）。
- 下流の BEACON パイプラインは古いキャッシュを使い続け、失敗せずに
  構造化 `warning` ログ行を出力する。
- 終了コード: `0` = 成功、`1` = HTTP/ネットワークエラー、`2` = JSON パースエラー。

### アラートガイダンス

繰り返しの失敗を検知するために `/var/log/beacon/misp_refresh.log` を監視すること。
推奨チェック:

1. **連続失敗（3 回以上）:** 3 日以上連続して `"event": "misp_cache_refresh.fetch_failed"`
   または `"misp_cache_refresh.http_error"` を検索する。

2. **キャッシュの鮮度:** キャッシュファイルの `_metadata.last_auto_sync` を確認する:

   ```bash
   python3 -c "import json; d=json.load(open('cache/misp-threat-actor.json')); \
       print(d.get('_metadata', {}).get('last_auto_sync', 'N/A'))"
   ```

   タイムスタンプが 7 日以上前の場合はアラートを発する。

3. **ログ形式:** すべての行は構造化 JSON（`structlog` 経由）。成功行の例:

   ```json
   {"event": "misp_cache_refresh.done", "output_path": "cache/misp-threat-actor.json",
    "last_auto_sync": "2026-05-23T03:00:01Z", "values_count": 994, "timestamp": "..."}
   ```

---

## SAGE 連携 — 手動 ETL 検証手順

本セクションは、BEACON が生成した PIR を SAGE に配置し、`pir_adjusted_criticality` が正しく更新されることを確認する手順を説明します。

---

### 前提条件

- SAGE が稼働しており、Spanner スキーマが初期化済み（SAGE/ で `make init-schema` 実行済み）
- SAGE の環境に `GCP_PROJECT_ID` および `SPANNER_INSTANCE_ID` が設定済み
- Spanner インスタンスへの書き込み権限がある
- BEACON で `pir_output.json` が生成済み（`beacon pir-generate` で生成）

---

### Step 1: PIR を生成する

```bash
cd BEACON/
beacon pir-generate \
  --context path/to/business_context.json \
  --output-dir output/
```

生成後、`pir_output.json` の内容を確認します:

```bash
cat pir_output.json | python -m json.tool
```

各 PIR エントリに含まれる必須フィールド:

| フィールド | 型 | 例 |
|-----------|----|----|
| `pir_id` | 文字列 | `"PIR-2026-001"` |
| `threat_actor_tags` | 文字列リスト | `["apt-china", "ransomware"]` |
| `asset_weight_rules` | 辞書リスト | `[{"tag": "plm", "criticality_multiplier": 2.5}]` |
| `valid_from` | ISO 日付文字列 | `"2026-04-04"` |
| `valid_until` | ISO 日付文字列 | `"2027-04-04"` |
| `intelligence_level` | 文字列 | `"strategic"` |

---

### Step 2: SAGE 互換性を検証する

バリデーターはスキーマチェックに加えて、タクソノミー照合・資産タグ一致・有効期間も検証します。

```bash
cd ../TRACE && uv run trace validate-pir --pir pir_output.json
# assets.json を併せて指定すると asset_weight_rules.tag の整合性も確認:
cd ../TRACE && uv run trace validate-pir --pir pir_output.json --assets assets.json
```

---

### Step 3: PIR を SAGE に配置する

`pir_output.json` を SAGE の `PIR_FILE_PATH` 環境変数が指すパスにコピーします:

```bash
# SAGE のデフォルト PIR パス（SAGE/src/sage/config.py の PIR_FILE_PATH を確認）
cp pir_output.json /path/to/sage/config/pir.json

# または環境変数で BEACON の出力を直接参照する:
export PIR_FILE_PATH=/path/to/beacon/pir_output.json
```

---

### Step 4: SAGE ETL を実行する

`SAGE/` ディレクトリで実行します:

```bash
cd ../SAGE && uv run sage run-etl
```

SAGE ETL は以下を実行します:
1. `PIRFilter.from_file()` で `pir_output.json` を読み込む
2. `threat_actor_tags` で STIX ThreatActor をフィルタリング（関連アクターのみ取り込み）
3. PIR の アクター × 資産タグ マッチングから `Targets` エッジを自動生成
4. `asset_weight_rules` を使って全資産の `pir_adjusted_criticality` を計算

ETL ログで確認すべき出力行:

```
pir_loaded          count=1
pir_filter_applied  relevant_actors=N  skipped=M
targets_generated   count=K
```

---

### Step 5: `pir_adjusted_criticality` を確認する

#### SAGE ビジュアライザー経由

```bash
cd ../SAGE && uv run sage visualize-graph
```

生成された HTML を開きます。PIR にマッチしたアクターが Targets エッジで紐づく資産は、
クリティカリティスコアが上昇しているはずです。

#### Spanner CLI 経由（gcloud）

```bash
gcloud spanner databases execute-sql sage-db \
  --instance=$SPANNER_INSTANCE_ID \
  --sql="SELECT id, name, criticality, pir_adjusted_criticality, tags
         FROM Asset
         ORDER BY pir_adjusted_criticality DESC
         LIMIT 20"
```

期待値: `tags` が PIR の `asset_weight_rules[*].tag` と重複している資産は
`pir_adjusted_criticality > criticality` となること。

#### 乗数の計算式

SAGE の計算式（`src/sage/pir/filter.py:adjust_asset_criticality`）:

```
pir_adjusted_criticality = min(base_criticality × max_matching_multiplier, 10.0)
```

Targets エッジが存在する場合（PIR マッチアクター → 資産）:

```
pir_adjusted_criticality = min(base × max_multiplier × 1.5, 10.0)
```

**例:** `tags=["plm"]`、`criticality=4.0`、PIR ルール `{"tag":"plm","criticality_multiplier":2.5}` の資産:
- Targets エッジなし: `min(4.0 × 2.5, 10.0) = 10.0`
- Targets エッジあり: `min(4.0 × 2.5 × 1.5, 10.0) = 10.0`（上限 cap）

---

### Step 6: Targets エッジを確認する

```bash
gcloud spanner databases execute-sql sage-db \
  --instance=$SPANNER_INSTANCE_ID \
  --sql="SELECT actor_stix_id, asset_id, confidence, source
         FROM Targets
         WHERE source = 'pir_auto'
         LIMIT 20"
```

各行が PIR から自動推定された 脅威アクター → 資産 の標的関係を表します。
`confidence`（0〜100）はアクターと PIR `threat_actor_tags` のタグ重複率を示します。

---

### トラブルシューティング

| 症状 | 考えられる原因 | 対処 |
|------|--------------|------|
| `pir_adjusted_criticality == criticality` | 資産タグが PIR `asset_weight_rules` と重複していない | Spanner の資産 `tags` と PIR `asset_weight_rules[*].tag` を照合 |
| `source='pir_auto'` の Targets 行がない | マッチするタグのアクターまたは資産がない | アクター取り込み完了を確認；`threat_actor_tags` のカバレッジを確認 |
| `pir_loaded count=0` | `PIR_FILE_PATH` が誤っているかファイルが空 | パスを確認して BEACON を再実行 |
| PIR バリデーション失敗 | 必須フィールドが欠けている | BEACON を再実行して `pir_output.json` を確認 |

---

### 推奨更新サイクル

| トリガー | 対応 |
|---------|------|
| 四半期定期レビュー | `business_context.json` を更新して BEACON を再実行 |
| M&A 発表 | `business_context.json` にトリガーを追加して PIR を再生成 |
| OT システム拡張 | クラウンジュエルとサプライチェーン情報を追加して PIR を再生成 |
| 主要な脅威アクターキャンペーン | `schema/threat_taxonomy.json` を更新して PIR を再生成 |
| 新規規制要件 | `organization.regulatory_context` を更新して PIR を再生成 |

再生成後は必ず `cd ../TRACE && uv run trace validate-pir` で検証してから SAGE に配置してください。

---

### Identity Asset 連携

BEACON は `identity_assets.json` も emit し、内部資産に対する identity 別
アクセス情報を表現します。SAGE は `HasAccess` エッジテーブルに取り込みます。
handoff には 2 つの field が伝搬します:

| Field | Producer | Consumer 効果 |
|-------|----------|---------------|
| `is_high_value_impersonation_target: bool` | HLD §4.3 に従い LLM が公開ブランド・公開露出のある幹部役職・critical supplier に対して true を設定 | `ImpersonatesIdentity` の `effective_priority` 計算式が、flag=true で multiplier=1.5 を無条件適用に切替。flag=false では `HIGH_VALUE_IMPERSONATION_ROLES` 15 entry frozenset との role-tag 交差にフォールバック。PIR L2 relevance score が、文書中に flag 付き identity 名が出現すると +0.2 boost。 |
| `impersonation_risk_factors: list[str]` | 自由形式タグ、例: `["public-facing-brand", "executive", "trusted-supplier"]` | SAGE `Identity` 行に保存しアナリスト dashboard 向けに使用。`effective_priority` の式自体には関与しない。 |

両 field とも optional default (`False` / `[]`)。設計詳細はプロジェクトルートの
`docs/initiative_c_attributed_impersonates.md` §11 を参照。
