# SAGE 連携 — 手動 ETL 検証手順

本ドキュメントは、BEACON が生成した PIR を SAGE に配置し、`pir_adjusted_criticality` が正しく更新されることを確認する手順を説明します。

---

## 前提条件

- SAGE が稼働しており、Spanner スキーマが初期化済み（SAGE/ で `make init-schema` 実行済み）
- SAGE の環境に `GCP_PROJECT_ID` および `SPANNER_INSTANCE_ID` が設定済み
- Spanner インスタンスへの書き込み権限がある
- BEACON で `pir_output.json` が生成済み（`uv run python cmd/generate_pir.py` で生成）

---

## Step 1: PIR を生成する

```bash
cd BEACON/
uv run python cmd/generate_pir.py \
  --context path/to/business_context.json \
  --output pir_output.json \
  --collection-plan collection_plan.md
```

生成後、`pir_output.json` の内容を確認します：

```bash
cat pir_output.json | python -m json.tool
```

各 PIR エントリに含まれる必須フィールド：

| フィールド | 型 | 例 |
|-----------|----|----|
| `pir_id` | 文字列 | `"PIR-2026-001"` |
| `threat_actor_tags` | 文字列リスト | `["apt-china", "ransomware"]` |
| `asset_weight_rules` | 辞書リスト | `[{"tag": "plm", "criticality_multiplier": 2.5}]` |
| `valid_from` | ISO 日付文字列 | `"2026-04-04"` |
| `valid_until` | ISO 日付文字列 | `"2027-04-04"` |
| `intelligence_level` | 文字列 | `"strategic"` |

---

## Step 2: SAGE 互換性を検証する

```bash
uv run python cmd/validate_pir.py --pir pir_output.json
```

バリデーターは必須フィールドと Pydantic モデルの制約をチェックします。
エラーがある場合は SAGE へ配置する前に修正してください。

---

## Step 3: PIR を SAGE に配置する

`pir_output.json` を SAGE の `PIR_FILE_PATH` 環境変数が指すパスにコピーします：

```bash
# SAGE のデフォルト PIR パス（SAGE/src/sage/config.py の PIR_FILE_PATH を確認）
cp pir_output.json /path/to/sage/config/pir.json

# または環境変数で BEACON の出力を直接参照する：
export PIR_FILE_PATH=/path/to/beacon/pir_output.json
```

---

## Step 4: SAGE ETL を実行する

`SAGE/` ディレクトリで実行します：

```bash
cd ../SAGE/
uv run python cmd/run_etl.py
```

SAGE ETL は以下を実行します：
1. `PIRFilter.from_file()` で `pir_output.json` を読み込む
2. `threat_actor_tags` で STIX ThreatActor をフィルタリング（関連アクターのみ取り込み）
3. PIR の アクター × 資産タグ マッチングから `Targets` エッジを自動生成
4. `asset_weight_rules` を使って全資産の `pir_adjusted_criticality` を計算

ETL ログで確認すべき出力行：

```
pir_loaded          count=1
pir_filter_applied  relevant_actors=N  skipped=M
targets_generated   count=K
```

---

## Step 5: `pir_adjusted_criticality` を確認する

### SAGE ビジュアライザー経由

```bash
uv run python cmd/visualize_graph.py
```

生成された HTML を開きます。PIR にマッチしたアクターが Targets エッジで紐づく資産は、
クリティカリティスコアが上昇しているはずです。

### Spanner CLI 経由（gcloud）

```bash
gcloud spanner databases execute-sql sage-db \
  --instance=$SPANNER_INSTANCE_ID \
  --sql="SELECT id, name, criticality, pir_adjusted_criticality, tags
         FROM Asset
         ORDER BY pir_adjusted_criticality DESC
         LIMIT 20"
```

期待値：`tags` が PIR の `asset_weight_rules[*].tag` と重複している資産は
`pir_adjusted_criticality > criticality` となること。

### 乗数の計算式

SAGE の計算式（`src/sage/pir/filter.py:adjust_asset_criticality`）：

```
pir_adjusted_criticality = min(base_criticality × max_matching_multiplier, 10.0)
```

Targets エッジが存在する場合（PIR マッチアクター → 資産）：

```
pir_adjusted_criticality = min(base × max_multiplier × 1.5, 10.0)
```

**例：** `tags=["plm"]`、`criticality=4.0`、PIR ルール `{"tag":"plm","criticality_multiplier":2.5}` の資産：
- Targets エッジなし：`min(4.0 × 2.5, 10.0) = 10.0`
- Targets エッジあり：`min(4.0 × 2.5 × 1.5, 10.0) = 10.0`（上限 cap）

---

## Step 6: Targets エッジを確認する

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

## トラブルシューティング

| 症状 | 考えられる原因 | 対処 |
|------|--------------|------|
| `pir_adjusted_criticality == criticality` | 資産タグが PIR `asset_weight_rules` と重複していない | Spanner の資産 `tags` と PIR `asset_weight_rules[*].tag` を照合 |
| `source='pir_auto'` の Targets 行がない | マッチするタグのアクターまたは資産がない | アクター取り込み完了を確認；`threat_actor_tags` のカバレッジを確認 |
| `pir_loaded count=0` | `PIR_FILE_PATH` が誤っているかファイルが空 | パスを確認して BEACON を再実行 |
| PIR バリデーション失敗 | 必須フィールドが欠けている | BEACON を再実行して `pir_output.json` を確認 |

---

## 推奨更新サイクル

| トリガー | 対応 |
|---------|------|
| 四半期定期レビュー | `business_context.json` を更新して BEACON を再実行 |
| M&A 発表 | `business_context.json` にトリガーを追加して PIR を再生成 |
| OT システム拡張 | クラウンジュエルとサプライチェーン情報を追加して PIR を再生成 |
| 主要な脅威アクターキャンペーン | `schema/threat_taxonomy.json` を更新して PIR を再生成 |
| 新規規制要件 | `organization.regulatory_context` を更新して PIR を再生成 |

再生成後は必ず `cmd/validate_pir.py` で検証してから SAGE に配置してください。
