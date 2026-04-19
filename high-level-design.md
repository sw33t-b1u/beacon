# BEACON — Business Environment Assessment for CTI Organizational Needs: High-Level Design

## 1. 目的とスコープ

企業の事業目的・プロジェクト・クラウン・ジュエルなどの組織情報（JSON/Markdown）を入力として受け取り、SAGEが消費できる **PIR（Priority Intelligence Requirements）JSON** を自動生成するシステム。

PIR は "Security が事業を守るための情報要件" であり、SAGE が適切な脅威アクタータグや資産重み係数を適用するための前提となる。BEACON は「事業文脈 → 情報要件 → CTI 優先度」の翻訳層を担う。

**対象外:**
- 脅威インテリジェンスの収集・分析（SAGE の責務）
- PIR 自体の実行監視（SAGE のクエリ・分析機能が担う）
- リアルタイム意思決定支援

---

## 2. 設計思想: Red Hat 5-Step PIR Methodology

[Red Hat PIR Dev](https://github.com/redhat-infosec/priority-intelligence-requirements-dev) に基づく5段階パイプラインを採用する。

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: ELEMENT EXTRACTION                                     │
│  事業コンテキスト → ビジネス要素（戦略目標・プロジェクト・規制）    │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  Step 2: ASSET MAPPING                                          │
│  ビジネス要素 → 依存する技術資産（ERP・クラウド・OT）              │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  Step 3: THREAT MAPPING                                         │
│  資産 → 関連する脅威オペレーション（ランサムウェア・諜報・SC攻撃）   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  Step 4: RISK SCORING                                           │
│  Likelihood × Impact マトリクスでPIR優先度を数値化               │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  Step 5: PIR GENERATION                                         │
│  SAGE 互換 PIR JSON + Markdown レポート + 情報収集計画           │
└─────────────────────────────────────────────────────────────────┘
```

Google Gen AI（Vertex AI Gemini）はStep 1・3・5において自然言語処理を補助し、アナリストの判断を自動化・拡張する。

---

## 3. システム全体構成

```
┌─────────────────────────────────────────────────────────────────┐
│                        INPUT                                    │
│                                                                 │
│  input/context.md         ユーザーが用意する唯一の入力ファイル    │
│                           (Organization Overview, Strategic     │
│                            Objectives, Current Projects,        │
│                            Crown Jewels, Critical Assets,       │
│                            Recent Security Incidents を記載)    │
│                                                                 │
│  schema/threat_taxonomy.json  業種×地域→脅威アクタータグ辞書    │
│  schema/asset_tags.json       資産種別→SAGE タグ辞書           │
│  docs/context_template.ja.md  入力テンプレート（追跡対象）       │
└──────────────────────────────┬──────────────────────────────────┘
                               │ LLM (gemini-2.5-flash-lite)
                               │ context_structuring.md プロンプト
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│               (中間出力 — オプション保存)                         │
│  output/business_context.json  構造化された入力 (--save-context) │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     BEACON PIPELINE (CLI)                       │
│                                                                 │
│  ingest/context_parser.py      JSON/MD を BusinessContext に変換   │
│  ingest/report_reader.py       PDF/URL/テキスト → プレーンテキスト  │
│  ingest/stix_extractor.py      LLM で STIX 2.1 オブジェクト抽出    │
│  analysis/element_extractor.py Step 1: 要素抽出                   │
│  analysis/asset_mapper.py      Step 2: 資産マッピング              │
│  analysis/assets_generator.py  CriticalAsset → SAGE assets.json  │
│  analysis/threat_mapper.py     Step 3: 脅威マッピング              │
│  analysis/risk_scorer.py       Step 4: リスクスコアリング          │
│  generator/pir_builder.py      Step 5: PIR JSON 生成              │
│  generator/report_builder.py   collection_plan.md 生成            │
│  llm/client.py                 Vertex AI Gemini クライアント       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        OUTPUT                                   │
│                                                                 │
│  output/pir_output.json        SAGE 互換 PIR（複数 PIR のリスト）  │
│  output/collection_plan.md     P3/P4 低優先度項目の収集計画一覧   │
│  output/business_context.json  構造化コンテキスト（任意保存）      │
│  output/assets.json            SAGE 互換 資産定義（generate_assets）│
│  output/stix_bundle.json       STIX 2.1 バンドル（stix_from_report）│
└─────────────────────────────────────────────────────────────────┘
```

> **注意**: `input/` および `output/` ディレクトリは `.gitignore` に含まれており、
> 機密性の高い運用データをリポジトリにコミットしない。
> テンプレートは `docs/context_template.ja.md` を参照。

---

## 4. 入力スキーマ: BusinessContext

### 4.1 business_context.json

```json
{
  "organization": {
    "name": "Example Corp",
    "industry": "manufacturing",          // NAICS 分類またはフリーテキスト
    "sub_industries": ["automotive", "aerospace"],
    "geography": ["Japan", "Southeast Asia", "Germany"],
    "employee_count_range": "1000-5000",
    "revenue_range_usd": "1B-10B",
    "stock_listed": true,
    "regulatory_context": ["APPI", "ISO27001", "TISAX"]
  },
  "strategic_objectives": [
    {
      "id": "OBJ-001",
      "title": "東南アジア市場への拡大",
      "description": "2027年までにタイ・ベトナムに製造拠点を設立",
      "timeline": "2025-2027",
      "sensitivity": "high",
      "key_decisions": ["現地パートナー選定", "M&A候補デューデリジェンス"]
    }
  ],
  "projects": [
    {
      "id": "PROJ-001",
      "name": "SAP S/4HANA 移行",
      "status": "in_progress",
      "sensitivity": "critical",
      "involved_vendors": ["SAP", "Accenture"],
      "cloud_providers": ["GCP"],
      "data_types": ["financial", "hr", "manufacturing"]
    }
  ],
  "crown_jewels": [
    {
      "id": "CJ-001",
      "name": "製品設計図（CADデータ）",
      "system": "PLM system",
      "business_impact": "critical",
      "exposure_risk": "medium"
    }
  ],
  "critical_assets": [
    {
      "id": "CA-001",
      "name": "SAP S/4HANA 本番システム",
      "type": "application",
      "function": "財務・製造・HR データを管理する基幹ERP",
      "hostname": "erp-prod-01.internal",
      "os_platform": "SUSE Linux Enterprise Server 15",
      "network_zone": "corporate",
      "criticality": "critical",
      "data_types": ["financial", "manufacturing", "hr"],
      "managing_vendor": "Accenture",
      "supply_chain_role": "",
      "dependencies": ["CA-002"],
      "exposure_risk": "medium"
    },
    {
      "id": "CA-002",
      "name": "Tier1サプライヤー EDIゲートウェイ",
      "type": "application",
      "function": "Tier1自動車サプライヤーとのEDI連携（部品発注・JIT調整）",
      "hostname": "",
      "os_platform": "",
      "network_zone": "ot",
      "criticality": "high",
      "data_types": ["manufacturing"],
      "managing_vendor": "Tier1サプライヤー名",
      "supply_chain_role": "tier1_supplier_edi_connectivity",
      "dependencies": [],
      "exposure_risk": "high"
    }
  ],
  "supply_chain": {
    "critical_vendors": ["Tier1サプライヤー名"],
    "cloud_providers": ["GCP", "AWS"],
    "ot_connectivity": true
  },
  "recent_incidents": [
    {
      "year": 2024,
      "type": "phishing",
      "impact": "low"
    }
  ]
}
```

### 4.2 threat_taxonomy.json（自動生成辞書）

**すべての内容を `cmd/update_taxonomy.py` が MITRE ATT&CK + MISP Galaxy から機械的に再生成する。**
手作業 curated な記述は一切含まず、個別出典が記録されていないフィールドは排除している。

**情報源（`_metadata.sources` に記録）:**

| ソース | URL | 用途 |
|--------|-----|------|
| MITRE ATT&CK Enterprise STIX | `raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json` | `mitre_groups`（intrusion-set 名・alias）+ `priority_ttps`（`relationship` 経由の TTP 収集）|
| MISP Galaxy threat-actor cluster | `raw.githubusercontent.com/MISP/misp-galaxy/main/clusters/threat-actor.json` | 国家帰属（`meta.country` / `cfr-suspected-state-sponsor`）・非 state 分類（`cfr-type-of-incident`）・標的業種・標的地域 |

**アクターカテゴリ軸:**
- `actor_categories.state_sponsored.<Country>` — MISP の `cfr-suspected-state-sponsor` / `meta.country` からクラスタリングした国家別バケット
- `actor_categories.espionage` — `cfr-type-of-incident` が Espionage / IP Theft に相当する非 state アクター
- `actor_categories.financial_crime` — Financial Crime / Ransomware / Cybercrime に相当する非 state アクター
- `actor_categories.sabotage` — Defacement / Denial of Service / Destructive / Wiper / Sabotage
- `actor_categories.subversion` — Influence operation / Disinformation / Hack and leak

**削除されたフィールド（旧バージョンからの breaking change）:**
- `industry_threat_map` — 業種 → カテゴリマッピングは `threat_mapper.py` にハードコードした `_BEACON_TO_MISP_INDUSTRY`（BEACON 業種 10 種 → MISP coarse 4 値）に置換
- `business_trigger_map` — 削除。トリガー昇格ロジックは `risk_scorer.py` 内の `{m_and_a, ot_connectivity, ipo_or_listing}` 定数セットに集約
- `supply_chain_threat_map` — 削除
- `actor_categories.*.subgroups`, `additional_tags`, `_metadata.last_manual_review` — 削除

**ジオグラフィマップ:** MISP `cfr-suspected-victims` を集計して `geography_threat_map[<geography>].{notable_groups, apt_tags}` を自動生成。

```json
{
  "_metadata": {
    "sources": {
      "mitre_attack": "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json",
      "misp_galaxy_threat_actor": "https://raw.githubusercontent.com/MISP/misp-galaxy/main/clusters/threat-actor.json"
    },
    "last_auto_sync": "2026-04-19T08:20:57+00:00",
    "generator": "cmd/update_taxonomy.py"
  },
  "actor_categories": {
    "state_sponsored": {
      "China": {
        "tags": ["apt-china"],
        "mitre_groups": ["APT10", "APT41", "MirrorFace", "Mustang Panda", "Volt Typhoon"],
        "priority_ttps": ["T1190", "T1566.001", "T1574.002", "T1041"],
        "target_industries": ["Private sector", "Government"],
        "target_geographies": ["Japan", "Taiwan", "United States"]
      },
      "Russia":      { "tags": ["apt-russia"],       "mitre_groups": [...], "priority_ttps": [...], "target_industries": [...], "target_geographies": [...] },
      "North Korea": { "tags": ["apt-north-korea"],  "mitre_groups": [...], "priority_ttps": [...], "target_industries": [...], "target_geographies": [...] },
      "Iran":        { "tags": ["apt-iran"],         "mitre_groups": [...], "priority_ttps": [...], "target_industries": [...], "target_geographies": [...] },
      "India":       { "tags": ["apt-india"],        "mitre_groups": [...], "priority_ttps": [...], "target_industries": [...], "target_geographies": [...] }
    },
    "espionage":       { "tags": ["espionage"],       "mitre_groups": [...], "priority_ttps": [...], "target_industries": [], "target_geographies": [] },
    "financial_crime": { "tags": ["financial-crime"], "mitre_groups": [...], "priority_ttps": [...], "target_industries": ["Private sector"], "target_geographies": ["Global"] },
    "sabotage":        { "tags": ["sabotage"],        "mitre_groups": [],    "priority_ttps": [],    "target_industries": [], "target_geographies": [] }
  },
  "geography_threat_map": {
    "Japan": {
      "notable_groups": ["APT10", "Lazarus Group", "MirrorFace"],
      "apt_tags": ["apt-china", "apt-north-korea"]
    }
  }
}
```

**マッチングロジック（`threat_mapper.py`）:**

1. BEACON 入力の `industry` を `_BEACON_TO_MISP_INDUSTRY` で MISP coarse category（`Private sector` / `Government` / `Military` / `Civil society`）に写像。
2. `actor_categories` 配下（state + 非 state）を走査。以下の両条件を満たすカテゴリを採用:
   - `target_industries` が空、または写像後の coarse category を含む
   - `target_geographies` が空・`Global`、または組織 geography とひとつ以上重なる
3. 採用したカテゴリから `tags` / `mitre_groups` / `priority_ttps` を集約。
4. 組織 geography ごとに `geography_threat_map[geo].{apt_tags, notable_groups}` を追加。

LLM フォールバック（旧 `_llm_fallback`）は削除済み。MISP カバレッジが広く辞書ヒットしないケースが稀で、LLM 出力の出典も記録できないためコードパス自体を廃止した。

---

## 5. 出力スキーマ: PIR JSON（SAGE 互換）

### 5.1 インテリジェンスレベルと有効期限

CTI の3層モデル（Bushido Token ブログ・FIRST CTI Curriculum 準拠）に基づいてPIRを分類し、有効期限を自動設定する。

| レベル | 対象 | 有効期限 | 例 |
|--------|------|---------|-----|
| `strategic` | 地政学的動向・業種リスク・長期的脅威アクター傾向 | 生成日 + 12ヶ月 | 「中国APTが製造業IPを標的にする可能性の監視」 |
| `operational` | 活動中キャンペーン・脅威グループ追跡・攻撃トレンド | 生成日 + 6ヶ月 | 「MirrorFaceの新規TTPとインフラ変化の監視」 |
| `tactical` | 特定TTP・IOC・活発な脆弱性悪用 | 生成日 + 1ヶ月 | 「CVE-2024-XXXX の製造業向け悪用状況の監視」 |

リスクスコアの `composite` 値によって推奨レベルを自動提案するが、アナリストが上書き可能。

### 5.2 PIR JSON スキーマ

```json
[
  {
    "pir_id": "PIR-2025-001",
    "intelligence_level": "strategic",
    "description": "主要製品設計図（CADデータ）を狙う国家支援アクターへの耐性強化",
    "rationale": "製造業×日本×OT接続の組み合わせにより MirrorFace / APT10 が高確率で活動中",
    "threat_actor_tags": ["espionage", "apt-china", "apt-north-korea"],
    "asset_weight_rules": [
      { "tag": "plm",            "criticality_multiplier": 2.5 },
      { "tag": "ot",             "criticality_multiplier": 2.0 },
      { "tag": "external-facing","criticality_multiplier": 1.8 }
    ],
    "collection_focus": [
      "MirrorFace / Earth Kasha の新規TTP観測",
      "製造業向けスピアフィッシングキャンペーン",
      "PLMシステムを標的とする脆弱性情報"
    ],
    "valid_from": "2025-01-01",
    "valid_until": "2026-01-01",
    "risk_score": {
      "likelihood": 4,
      "impact": 5,
      "composite": 20
    },
    "source_elements": ["CJ-001", "OBJ-001", "PROJ-001"]
  },
  {
    "pir_id": "PIR-2025-002",
    "intelligence_level": "operational",
    "description": "SAP S/4HANA 移行期間中のクラウド設定ミスとサプライチェーンリスクの監視",
    "rationale": "クラウド移行中の設定ミスおよび参画ベンダー（Accenture等）経由の侵入経路を想定",
    "threat_actor_tags": ["financial-crime", "apt-russia"],
    "asset_weight_rules": [
      { "tag": "erp",            "criticality_multiplier": 2.5 },
      { "tag": "cloud",          "criticality_multiplier": 1.8 },
      { "tag": "financial",      "criticality_multiplier": 2.0 }
    ],
    "collection_focus": [
      "SAP関連脆弱性CVEの悪用情報",
      "GCP環境を標的とするランサムウェアキャンペーン",
      "Accentureおよび関連SIのインシデント情報"
    ],
    "valid_from": "2025-01-01",
    "valid_until": "2025-07-01",
    "risk_score": {
      "likelihood": 3,
      "impact": 5,
      "composite": 15
    },
    "source_elements": ["PROJ-001"]
  }
]
```

`risk_score.composite = likelihood × impact`（各1-5スケール、最大25）

### 5.3 インテリジェンスレベル推奨ロジック

| composite スコア | 推奨 level |
|-----------------|-----------|
| 20-25 | `strategic` |
| 12-19 | `operational` |
| 1-11 | `tactical` |

ただし `business_context.json` の `business_triggers` に `m_and_a` / `ot_connectivity` / `ipo_or_listing` のいずれかが指定されている場合は、スコアに関わらず `operational` 以上に自動昇格する。このトリガー集合は `src/beacon/analysis/risk_scorer.py` の `_recommend_level()` にハードコードされている（MITRE/MISP 由来のタクソノミーには含めず、BEACON 固有の運用ルールとして分離）。トリガー選定の根拠は、事業イベントと同期して攻撃面が急拡大することが CTI ベンダーレポート（Mandiant M-Trends、MSTIC Digital Defense Report 等）で繰り返し指摘されていることによる。

**注:** `tactical` が生成されるのは `composite < 12` かつ `{m_and_a, ot_connectivity, ipo_or_listing}` のいずれも立たない場合のみ。多くの組織は何らかのトリガーが立つため、実運用では `tactical` の発生は稀。

---

## 6. LLM 統合（Vertex AI — Gemini）

SAGE と同じ GCP プロジェクトで動作する Vertex AI を LLM バックエンドとして使用する。
`google-genai` SDK（Google Gen AI SDK）経由で Gemini モデルを呼び出す。
認証は Application Default Credentials（ADC）を利用し、APIキーの管理が不要。

### 6.1 モデル割り当て

タスクの複雑度に応じてモデルを使い分け、コストと品質を最適化する。

| 処理 | タスク性質 | モデル | 理由 |
|------|-----------|--------|------|
| コンテキスト構造化（MD → JSON） | 単純・高速 | `gemini-2.5-flash-lite` | スキーマに従った変換のみ。推論不要。コスト最優先。 |
| 脅威タグ補完（辞書ミスマッチ時） | 単純・短文 | `gemini-2.5-flash-lite` | 辞書にない業種・地域への補完。短い出力。 |
| PIR 文章生成（description・rationale・collection_focus） | 中程度 | `gemini-2.5-flash` | 事業要素と脅威情報を組み合わせた文章生成。バランス型。 |
| リスクスコアリング補助（辞書に根拠なし時） | 複雑・推論 | `gemini-2.5-pro` | Likelihood / Impact の定性的判断に CTI 知識が必要。 |

各モデルは環境変数で個別に上書き可能（後述）。

### 6.2 Vertex AI 設定

```python
# src/beacon/llm/client.py（概要）
from google import genai
from google.genai import types as genai_types

client = genai.Client(vertexai=True, project=config.gcp_project_id, location=config.vertex_location)

# タスク種別ごとにモデルを切り替える
model_map = {
    "simple":  config.llm_model_simple,   # gemini-2.5-flash-lite
    "medium":  config.llm_model_medium,   # gemini-2.5-flash
    "complex": config.llm_model_complex,  # gemini-2.5-pro
}
response = client.models.generate_content(
    model=model_map[task],
    contents=prompt,
    config=genai_types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
)
```

必要な環境変数:

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `GCP_PROJECT_ID` | — | SAGE と共用可 |
| `VERTEX_LOCATION` | `us-central1` | 米国中部リージョン（コスト最安） |
| `BEACON_LLM_SIMPLE` | `gemini-2.5-flash-lite` | 単純タスク用モデル |
| `BEACON_LLM_MEDIUM` | `gemini-2.5-flash` | 中程度タスク用モデル |
| `BEACON_LLM_COMPLEX` | `gemini-2.5-pro` | 複雑推論タスク用モデル |

**リージョン選定の理由**: Vertex AI の Gemini モデルは `us-central1` が最も広くサポートされており、他リージョンより低コスト。レイテンシが許容できる内部バッチ処理（PIR生成は非リアルタイム）であれば米国リージョンで問題ない。機密データをリージョン外に出せない場合は `asia-northeast1`（東京）に変更する。

### 6.3 プロンプト設計方針

- 全プロンプトは **JSON モード**（`response_mime_type="application/json"`）で呼び出し、後処理パースを簡略化する
- システムプロンプトは `src/beacon/llm/prompts/` ディレクトリに Markdown ファイルとして管理し、コードと分離する
- 機密性の高い入力が含まれる場合を想定し、プロンプトにはできる限り匿名化した要素のみを渡す

### 6.4 LLM を使わないパス（`--no-llm` フラグ）

辞書マッチングのみで PIR を生成する。Vertex AI への接続が不要なため、エアギャップ環境・機密性の高い入力・コスト制約のある環境に適している。この場合、Markdown 入力は受け付けず JSON 入力のみ対応する。

---

## 7. リスクスコアリング（Step 4）

Red Hat方式のLikelihood × Impact マトリクスを採用する。

### Likelihood スコア（1-5）

| スコア | 判断基準 |
|--------|---------|
| 5 | 業種×地域マッチのAPTが過去12ヶ月内に類似組織を攻撃している |
| 4 | 業種マッチの汎用脅威（ランサムウェアグループ等）が活発 |
| 3 | 業種または地域のどちらかのみマッチ |
| 2 | 間接的な関連（サプライチェーン経由等） |
| 1 | 証拠が弱い・関連性が低い |

### Impact スコア（1-5）

| スコア | 判断基準 |
|--------|---------|
| 5 | 事業継続不能・クラウン・ジュエル喪失・上場企業の場合は開示義務発生 |
| 4 | 主要システム停止・機密情報漏洩・法的リスク |
| 3 | 業務停止（部門単位）・顧客影響あり |
| 2 | 内部業務への軽微な影響 |
| 1 | 回復可能・外部影響なし |

### 優先度分類

| composite | 優先度 | 対応 |
|-----------|--------|------|
| 20-25 | P1 Critical | 即時PIR作成・毎月レビュー |
| 12-19 | P2 High | PIR作成・四半期レビュー |
| 6-11  | P3 Medium | 監視継続・半期レビュー |
| 1-5   | P4 Low | ウォッチリスト |

P1/P2 のみ SAGE PIR JSON として出力する（P3以下は `collection_plan.md` に記録）。

---

## 8. ディレクトリ構成

```
BEACON/
├── high-level-design.md       # 本文書
├── pyproject.toml             # uv + ruff（依存関係一覧）
├── Makefile                   # check / generate / validate / format
├── .env.example               # 環境変数サンプル（GCP_PROJECT_ID 等）
├── input/                     # ← .gitignore 対象（機密データ）
├── output/                    # ← .gitignore 対象（生成物）
│   ├── pir_output.json        # SAGE 互換 PIR 出力
│   ├── collection_plan.md     # P3/P4 収集計画
│   ├── business_context.json  # 中間出力（--save-context 指定時）
│   ├── assets.json            # SAGE 互換資産定義（generate_assets）
│   └── stix_bundle.json       # STIX 2.1 バンドル（stix_from_report）
├── src/beacon/
│   ├── config.py              # 環境変数ベース設定（GCP_PROJECT_ID, VERTEX_LOCATION 等）
│   ├── ingest/
│   │   ├── schema.py          # BusinessContext / CriticalAsset 等 Pydantic モデル
│   │   ├── context_parser.py  # JSON/MD → BusinessContext に変換
│   │   ├── report_reader.py   # PDF/URL/テキスト → Markdown（markitdown）
│   │   └── stix_extractor.py  # LLM で STIX 2.1 オブジェクト抽出・バンドル生成
│   ├── analysis/
│   │   ├── element_extractor.py   # Step 1: 要素抽出（critical_assets 含む）
│   │   ├── asset_mapper.py        # Step 2: 資産タグマッピング
│   │   ├── assets_generator.py    # CriticalAsset → SAGE assets.json 変換
│   │   ├── threat_mapper.py       # Step 3: 脅威マッピング（MITRE+MISP 辞書マッチングのみ）
│   │   └── risk_scorer.py         # Step 4: Likelihood × Impact スコアリング
│   ├── generator/
│   │   ├── pir_builder.py         # Step 5: PIR JSON 生成
│   │   └── report_builder.py      # collection_plan.md 生成（P3/P4 低優先度項目）
│   ├── llm/
│   │   ├── client.py              # Vertex AI Gemini クライアント（google-genai SDK）
│   │   └── prompts/
│   │       ├── context_structuring.md    # context.md → BusinessContext JSON 変換
│   │       ├── pir_generation.md         # PIR 文章生成
│   │       └── stix_extraction.md        # CTI レポート → STIX 2.1 オブジェクト抽出
│   ├── review/
│   │   └── github.py              # GHE/GitHub Issue 作成・PIR レビュー依頼
│   ├── sage/
│   │   └── client.py              # SAGE Analysis API クライアント
│   └── web/
│       ├── app.py                 # FastAPI ルーティング（GET / POST /generate /review）
│       ├── session.py             # セッション管理（$TMPDIR/beacon_session_*.json）
│       └── templates/             # Jinja2 HTML テンプレート
├── cmd/
│   ├── generate_pir.py        # PIR 生成 CLI（input/context.md → output/）
│   ├── generate_assets.py     # CriticalAsset → SAGE assets.json 変換 CLI
│   ├── stix_from_report.py    # PDF/URL → STIX 2.1 バンドル抽出 CLI
│   ├── validate_pir.py        # PIR JSON SAGE 互換スキーマ検証
│   ├── generate_schemas.py    # Pydantic から JSONSchema を自動生成
│   ├── update_taxonomy.py     # MITRE ATT&CK STIX から脅威タクソノミーを自動更新
│   ├── submit_for_review.py   # GHE Issue 作成（PIR レビュー依頼）
│   └── web_app.py             # Web UI 起動（uvicorn）
├── schema/
│   ├── threat_taxonomy.json           # MITRE+MISP 由来の脅威タクソノミー（自動生成）
│   ├── asset_tags.json                # 資産種別 → SAGE タグ辞書
│   ├── content_ja.json                # 日本語コンテンツ辞書
│   ├── trigger_keywords.json          # ビジネストリガーキーワード辞書
│   ├── business_context.schema.json   # BusinessContext JSONSchema
│   └── pir_output.schema.json         # PIR 出力 JSONSchema
├── tests/
│   ├── fixtures/
│   │   ├── sample_context_manufacturing.json
│   │   ├── sample_context_finance.md
│   │   └── sample_stix_bundle.json
│   └── test_*.py
└── docs/
    ├── setup.md
    ├── setup.ja.md
    ├── context_template.md
    ├── context_template.ja.md
    ├── data-model.md
    ├── data-model.ja.md
    ├── dependencies.md
    ├── dependencies.ja.md
    ├── sage_integration.md
    └── sage_integration.ja.md
```

### 主要依存関係

| パッケージ | 用途 |
|-----------|------|
| `pydantic>=2.0` | BusinessContext・PIR の入出力スキーマ検証 |
| `google-genai>=1.0` | Google Gen AI SDK による Vertex AI Gemini 呼び出し |
| `structlog` | 構造化ログ（SAGE と共通） |
| `httpx>=0.27.0` | MITRE CTI STIX 取得・SAGE API ポーリング |
| `fastapi>=0.111.0` | Web UI フレームワーク |
| `uvicorn[standard]>=0.30.0` | ASGI サーバー |
| `python-multipart>=0.0.9` | ファイルアップロード（multipart/form-data） |
| `jinja2>=3.1.0` | Web UI HTML テンプレートレンダリング |
| `markitdown[pdf]>=0.1.0` | PDF/URL → クリーン Markdown 変換（stix_from_report） |

---

## 9. CLI インターフェース

```bash
# --- PIR 生成 ---

# 標準フロー: input/context.md → output/pir_output.json + output/collection_plan.md
uv run python cmd/generate_pir.py

# 中間ファイル(business_context.json)も保存
uv run python cmd/generate_pir.py \
  --save-context output/business_context.json

# 入力ファイルを明示指定
uv run python cmd/generate_pir.py \
  --context input/context.md \
  --output output/pir_output.json \
  --collection-plan output/collection_plan.md

# LLM なし（辞書のみ、エアギャップ環境向け / JSON 入力のみ）
uv run python cmd/generate_pir.py \
  --context input/business_context.json \
  --no-llm

# PIR JSON が SAGE 互換かを検証
uv run python cmd/validate_pir.py --pir output/pir_output.json

# --- アセット生成 ---

# Markdown コンテキストから assets.json を生成（LLM / Vertex AI が必要）
uv run python cmd/generate_assets.py --context input/context.md

# JSON コンテキストから生成（LLM 不要）
uv run python cmd/generate_assets.py \
  --context input/context.json \
  --no-llm \
  --output output/assets.json

# --- CTI レポート → STIX バンドル ---

# PDF から生成
uv run python cmd/stix_from_report.py --input report.pdf

# Web 記事 URL から生成（zsh/bash では ? & = が特殊文字のためシングルクォートで囲む）
uv run python cmd/stix_from_report.py --input 'https://example.com/apt-analysis?id=1'

# 高精度モデルを使用（遅い: 2〜5分）
uv run python cmd/stix_from_report.py --input report.pdf --task complex

# 長いレポート向けに入力サイズを増やす（デフォルト: 10000文字）
uv run python cmd/stix_from_report.py --input report.pdf --max-chars 30000

# --- その他 ---

# 脅威タクソノミーを MITRE ATT&CK STIX から自動更新
uv run python -m cmd.update_taxonomy [--dry-run]

# GHE Issue 作成（PIR アナリストレビュー依頼）
uv run python cmd/submit_for_review.py --pir output/pir_output.json

# Web UI 起動
uv run python cmd/web_app.py --port 8080

# Pydantic から JSONSchema を生成（schema/*.schema.json に出力）
uv run python cmd/generate_schemas.py
```

---

## 10. SAGE との連携フロー

```
[アナリスト]
  │ 事業コンテキスト文書を作成・更新
  ▼
[BEACON: generate_pir]
  │ pir_output.json を生成
  ▼
[アナリストレビュー]
  │ report.md を確認・必要に応じて手動編集
  ▼
[SAGE PIR ファイルへ配置]
  │ cp pir_output.json /config/pir.json  （SAGE の PIR_FILE_PATH）
  ▼
[SAGE ETL 実行]
  │ PIR に基づいて Targets エッジ生成・pir_adjusted_criticality 更新
  ▼
[SAGE Analysis API]
  │ チョークポイント・攻撃経路クエリに PIR 重みが反映される
```

更新頻度の目安: 四半期に1回、または重大な組織変更（M&A・新規プロジェクト開始）の都度。

---

## 11. 設計上のトレードオフと未解決事項

| 項目 | 採用方針 | 代替案 |
|------|---------|--------|
| 辞書 vs LLM | 辞書ファースト + LLM補完（`--no-llm` で切り離し可能） | LLMのみ（辞書不要だが品質が一定しない） |
| SAGE スキーマ互換性 | SAGE の PIR JSON スキーマに準拠（`pir_id`, `threat_actor_tags`, `asset_weight_rules` を必須） | BEACON 独自スキーマ + SAGE変換レイヤー（複雑になる） |
| 入力検証 | Pydantic v2 でスキーマ検証 | JSONSchema のみ（Pydantic は依存追加になる） |
| Likelihood の自動算出 | 辞書の業種×地域マッチングで半自動（アナリストが最終確認） | SAGE Spanner から実際の脅威アクター観測データを参照して自動化（Phase 2 候補） |

**設計上の決定事項（確認済み）:**
- PIR 有効期限: インテリジェンスレベルで自動設定（strategic: +12ヶ月 / operational: +6ヶ月 / tactical: +1ヶ月）
- Pydantic v2 を入力バリデーションに採用（クロスフィールドバリデーションは Phase 3 SAGE連携検証時に追加）
- LLM バックエンド: Vertex AI Gemini（ADC認証、GCP プロジェクト共用）
- モデル: タスク複雑度別（simple: `gemini-2.5-flash-lite` / medium: `gemini-2.5-flash` / complex: `gemini-2.5-pro`）
- デフォルトリージョン: `us-central1`（コスト最安）。変更は環境変数 `VERTEX_LOCATION` で対応
- `gemini-2.5-pro` のコストは許容範囲
- MD→JSON変換: ワンショット（全文を1回のLLM呼び出しで変換）
- PIR文章生成: 辞書ベース結果をコンテキストとしてLLMに渡し拡充（Phase 1結果を上書きではなく改善）
- `report_builder.py` の範囲: `collection_plan.md`（P3/P4低優先度項目の収集計画一覧）のみ。PIRの `description`/`rationale` は `pir_builder.py` が担うため重複しない
- SAGE連携検証: Spanner実環境なしで実施できるスキーマ静的検証（pytest）を採用。手動ETL検証手順は `docs/sage_integration.md` に記載
- テスト戦略: `unittest.mock` でモック（`make check` 対象）+ `@pytest.mark.integration` で実APIテスト分離（`make test-integration`）

**その他の未解決事項は `TODO.md` を参照。**

---

*実装フェーズは `TODO.md` を参照。設計変更は実装前に本文書を更新すること。*
