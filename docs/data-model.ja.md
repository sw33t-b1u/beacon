# BEACON — データモデル

英語版（正本）: [`docs/data-model.md`](data-model.md)

## 入力: BusinessContext JSON

戦略ドキュメントを `input/context.md` として配置してください（[`docs/context_template.ja.md`](context_template.ja.md) 参照）。
LLM が Markdown を構造化 `BusinessContext` JSON に変換します。`--save-context` で中間 JSON を確認できます。

```json
{
  "organization": {
    "name": "Example Corp",
    "industry": "manufacturing",
    "geography": ["Japan", "Southeast Asia"],
    "stock_listed": true,
    "regulatory_context": ["APPI", "ISO27001"]
  },
  "crown_jewels": [
    {
      "id": "CJ-001",
      "name": "製品設計データ（CAD）",
      "system": "PLM システム",
      "business_impact": "critical",
      "exposure_risk": "medium"
    }
  ],
  "critical_assets": [
    {
      "id": "CA-001",
      "name": "SAP ERP 本番環境",
      "type": "application",
      "function": "財務・製造オペレーションの中核 ERP",
      "hostname": "sap-prod-01",
      "os_platform": "SLES 15",
      "network_zone": "corporate",
      "criticality": "critical",
      "data_types": ["financial", "pii"],
      "managing_vendor": "SAP SE",
      "supply_chain_role": "",
      "dependencies": ["CA-002"],
      "exposure_risk": "medium"
    }
  ],
  "supply_chain": {
    "ot_connectivity": true,
    "cloud_providers": ["GCP"]
  }
}
```

### CriticalAsset フィールド一覧

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `id` | string | アセット識別子（例: `CA-001`） |
| `name` | string | アセット名 |
| `type` | enum | `server`, `database`, `network_device`, `application`, `endpoint`, `storage`, `identity_system`, `ot_device`, `cloud_service`, `other` |
| `function` | string | ビジネス機能の説明（タグ推定のキーワード照合に使用） |
| `hostname` | string | ホスト名または FQDN（任意） |
| `os_platform` | string | OS またはプラットフォーム（任意） |
| `network_zone` | enum | `internet`, `dmz`, `corporate`, `ot`, `cloud`, `restricted`, `unknown` |
| `criticality` | enum | `low`, `medium`, `high`, `critical` |
| `data_types` | list[string] | 保存・処理するデータ種別（例: `pii`, `financial`, `phi`） |
| `managing_vendor` | string | 管理ベンダー（アクティブベンダーシグナルとして使用） |
| `supply_chain_role` | string | サプライチェーン上の役割（例: `tier1-supplier-gateway`） |
| `dependencies` | list[string] | 依存するアセットの ID リスト |
| `exposure_risk` | enum | `low`, `medium`, `high`, `critical` |

完全なスキーマ: `schema/business_context.schema.json`（`uv run python cmd/generate_schemas.py` で生成）

---

## 出力: PIR JSON（SAGE 互換）

```json
[
  {
    "pir_id": "PIR-2026-001",
    "intelligence_level": "strategic",
    "description": "製造業×日本 環境のクラウンジュエル（PLM system）を狙う脅威アクターへの耐性強化",
    "rationale": "Likelihood=5, Impact=5 — 業種×地域マッチ: state_sponsored.China, ransomware / OT接続によるラテラルムーブリスクあり",
    "threat_actor_tags": ["apt-china", "espionage", "ip-theft", "ot-targeting", "ransomware"],
    "asset_weight_rules": [
      { "tag": "plm", "criticality_multiplier": 2.5 },
      { "tag": "ot",  "criticality_multiplier": 2.0 }
    ],
    "collection_focus": [
      "MirrorFace / APT10 の新規TTP・インフラ変化の観測",
      "OT/ICS環境を標的とする脆弱性悪用情報"
    ],
    "valid_from": "2026-04-04",
    "valid_until": "2027-04-04",
    "risk_score": { "likelihood": 5, "impact": 5, "composite": 25 }
  }
]
```

完全なスキーマ: `schema/pir_output.schema.json`（`uv run python cmd/generate_schemas.py` で生成）

> **注意:** `--no-llm` モードでは英語で出力されます。LLM 拡充が有効（デフォルト）の場合、`description`・`rationale`・`collection_focus` は Vertex AI Gemini によって書き換えられ、組織の言語コンテキストに合わせた表現になります。

---

## PIR 優先度フィルタリング

`pir_output.json` には P1 と P2 のみが含まれます。P3 は `collection_plan.md`（`--collection-plan` で生成）に記録されます。

| 優先度 | composite スコア | 典型例 |
|-------|-----------------|-------|
| P1 | ≥ 20 | 業種クラウンジュエルを標的とする国家支援型 APT |
| P2 | 12–19 | 業種を狙う進行中のランサムウェアキャンペーン |
| P3（計画のみ） | 1–11 | 業種関連性の低い一般的な CVE 情報 |

---

## コレクションプラン（collection_plan.md）

`collection_plan.md` は `pir_output.json` と並行して生成される Markdown レポートです。P1/P2 の閾値に達しなかった項目を記録し、CTI チームの運用収集スケジュールとして機能します。

**生成コマンド:**

```bash
uv run python cmd/generate_pir.py --context ... --output pir_output.json \
  --collection-plan collection_plan.md
```

**内容:**

| セクション | 説明 |
|-----------|------|
| P3 監視項目 | P2 閾値未満の脅威。即時対応は不要だが継続監視が必要な項目 |
| トリガー別アクション | ビジネストリガー（M&A・OT拡張・IPO）に対応する収集アクション |
| 収集頻度テーブル | フィードタイプ別の月次/週次/日次スケジュール（CTI チーム向け） |

`collection_plan.md` は `.gitignore` に登録済み（実行時出力のためコミット対象外）。

---

## インテリジェンスレベルと有効期間

| レベル | composite | valid_until | 例 |
|--------|-----------|-------------|-----|
| `strategic` | 20–25 | +12 ヶ月 | 業種 IP を標的とする国家支援型 APT |
| `operational` | 12–19 | +6 ヶ月 | 進行中のランサムウェアキャンペーン |
| `tactical` | 1–11 | +1 ヶ月 | 特定 CVE の悪用 |

ビジネストリガー（M&A、OT 接続、IPO）はスコアに関わらず `tactical` → `operational` にエスカレーションできます。

---

## LLM 連携（Vertex AI Gemini）

| ステップ | トリガー | モデル |
|---------|---------|-------|
| MD → BusinessContext（`parse_markdown`） | `.md` 入力 | `gemini-2.5-flash-lite` |
| 脅威タグ補完（`map_threats`） | 辞書: 0 マッチ | `gemini-2.5-flash-lite` |
| PIR テキスト拡充（`build_pirs`） | `use_llm=True` 常時 | `gemini-2.5-flash` |
| 可能性スコアリング補助（`score`） | 辞書: 根拠なし | `gemini-2.5-pro` |

認証は Application Default Credentials（ADC）を使用します。API キー管理は不要です。

---

## 脅威タクソノミーカバレッジ

`schema/threat_taxonomy.json` は次の 2 つのソースから完全に自動生成されます:

- **MITRE ATT&CK Enterprise**（`intrusion-set`、`attack-pattern`、`uses` リレーションシップ） — カノニカルなグループ名と priority TTP
- **MISP Galaxy `threat-actor` クラスタ**（`cfr-suspected-state-sponsor`、`cfr-type-of-incident`、`cfr-suspected-victims`、`country`） — 国家帰属・非国家アクターの動機・標的業種/地域

カテゴリ軸:

| 軸 | バケット |
|----|---------|
| `state_sponsored.<Country>` | MISP `cfr-suspected-state-sponsor` のカノニカル国名（例: China、Russia、North Korea、Iran、India、South Korea、Vietnam、United States）。別名は正規化（例: `USA` → `United States`）。 |
| 非国家 | `espionage`、`financial_crime`、`sabotage`、`subversion` — MISP `cfr-type-of-incident` から派生。 |

各バケットが保持する情報:

- `tags` — `apt-china`、`financial-crime` 等の短いラベル（国家バケットは `apt-<country-slug>`）
- `mitre_groups` — MITRE ATT&CK のカノニカルなグループ名
- `priority_ttps` — `uses` リレーションでリンクされた MITRE technique ID
- `target_industries` — MISP の粗粒度業種（`Private sector`、`Government`、`Military`、`Civil society`）
- `target_geographies` — MISP `cfr-suspected-victims` の国名リスト

**業種マッチング**は BEACON ⇄ MISP の粗写像（`threat_mapper._BEACON_TO_MISP_INDUSTRY`）で実施:

| BEACON 業種 | MISP 区分 |
|-----------|----------|
| defense | Military |
| government | Government |
| education | Civil society |
| manufacturing, finance, energy, healthcare, technology, logistics, other | Private sector |

**地域マッチング**は `target_geographies` が空または `Global` の場合「すべて受理」、それ以外は組織の地域と重なり必須。

正規の feed から再生成:

```bash
uv run python cmd/update_taxonomy.py [--dry-run]
```

JSON 内の `_metadata.sources` にカノニカルな fetch URL が記録されます。手動 curated レイヤーは存在せず、全内容が上流 feed 由来のため、`update_taxonomy.py` は決定論的に再構築できます。
