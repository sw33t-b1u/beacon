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

LLM（Claude API）はStep 1・3・5において自然言語処理を補助し、アナリストの判断を自動化・拡張する。

---

## 3. システム全体構成

```
┌─────────────────────────────────────────────────────────────────┐
│                        INPUT                                    │
│                                                                 │
│  [business_context.json]  事業構造・目標・資産・規制を構造化入力  │
│  [context.md]             自然言語の戦略文書（LLMで構造化）       │
│  [threat_taxonomy.json]   業種×地域→脅威アクタータグ辞書         │
│  [asset_tags.json]        資産種別→SAGE タグ辞書               │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     BEACON PIPELINE (CLI)                       │
│                                                                 │
│  ingest/context_parser.py   JSON/MD を BusinessContext に変換   │
│  analysis/element_extractor.py  Step 1: 要素抽出               │
│  analysis/asset_mapper.py       Step 2: 資産マッピング          │
│  analysis/threat_mapper.py      Step 3: 脅威マッピング          │
│  analysis/risk_scorer.py        Step 4: リスクスコアリング       │
│  generator/pir_builder.py       Step 5: PIR JSON 生成          │
│  generator/report_builder.py    collection_plan.md 生成         │
│  llm/client.py                  Vertex AI Gemini クライアント   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        OUTPUT                                   │
│                                                                 │
│  [pir_output.json]    SAGE 互換 PIR（複数 PIR のリスト）          │
│  [collection_plan.md] P3/P4 低優先度項目の収集計画一覧           │
└─────────────────────────────────────────────────────────────────┘
```

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

### 4.2 threat_taxonomy.json（辞書ファイル）

MITRE ATT&CK Groups、Bushido Token ブログ（Big 4 国家支援分類）、EternalLiberty プロジェクトを参考に構築する辞書。
動機ベースのカテゴリ（国家支援 / ランサムウェア / ハクティビスト）を軸とし、業種・地域でフィルタリングする。

```json
{
  "actor_categories": {
    "state_sponsored": {
      "China": {
        "tags": ["apt-china", "espionage", "ip-theft"],
        "target_industries": ["manufacturing", "defense", "technology", "aerospace"],
        "target_geographies": ["Japan", "Southeast Asia", "USA", "Europe"],
        "mitre_groups": ["APT10", "APT41", "MirrorFace", "Mustang Panda"],
        "priority_ttps": ["T1190", "T1566.001", "T1574.002", "T1041"]
      },
      "Russia": {
        "tags": ["apt-russia", "espionage", "destructive"],
        "target_industries": ["energy", "defense", "government", "finance"],
        "target_geographies": ["Europe", "USA", "Ukraine"],
        "mitre_groups": ["APT28", "APT29", "Sandworm"],
        "priority_ttps": ["T1566", "T1078", "T1486"]
      },
      "North Korea": {
        "tags": ["apt-north-korea", "financially-motivated", "cryptocurrency"],
        "target_industries": ["finance", "cryptocurrency", "defense", "technology"],
        "target_geographies": ["Japan", "South Korea", "USA"],
        "mitre_groups": ["Lazarus", "Kimsuky", "APT38"],
        "priority_ttps": ["T1059", "T1566", "T1041"]
      },
      "Iran": {
        "tags": ["apt-iran", "espionage", "hacktivism"],
        "target_industries": ["energy", "government", "defense"],
        "target_geographies": ["Middle East", "USA", "Israel"],
        "mitre_groups": ["APT33", "APT34", "Charming Kitten"],
        "priority_ttps": ["T1566", "T1190", "T1078"]
      }
    },
    "ransomware": {
      "tags": ["ransomware", "financially-motivated", "raas"],
      "target_industries": ["healthcare", "manufacturing", "finance", "education", "logistics"],
      "target_geographies": ["Global"],
      "mitre_groups": ["LockBit", "RansomHub", "BlackCat", "INC Ransomware"],
      "priority_ttps": ["T1190", "T1078", "T1003.001", "T1486"]
    },
    "hacktivist": {
      "tags": ["hacktivism", "ideological", "ddos"],
      "target_industries": ["government", "energy", "finance", "media"],
      "target_geographies": ["Context-dependent"],
      "mitre_groups": [],
      "priority_ttps": ["T1498", "T1499", "T1491"]
    }
  },
  "industry_threat_map": {
    "manufacturing": {
      "applicable_categories": ["state_sponsored.China", "state_sponsored.North Korea", "ransomware"],
      "additional_tags": ["ip-theft", "ot-targeting"],
      "priority_ttps": ["T1190", "T1078", "T1486", "T1566.001"]
    },
    "finance": {
      "applicable_categories": ["state_sponsored.North Korea", "ransomware"],
      "additional_tags": ["fraud", "swift-targeting"],
      "priority_ttps": ["T1059", "T1566", "T1041"]
    },
    "energy": {
      "applicable_categories": ["state_sponsored.Russia", "state_sponsored.Iran", "ransomware"],
      "additional_tags": ["critical-infrastructure", "ot-targeting"],
      "priority_ttps": ["T1190", "T1078", "T1486"]
    },
    "healthcare": {
      "applicable_categories": ["ransomware"],
      "additional_tags": ["phi-targeting"],
      "priority_ttps": ["T1190", "T1486", "T1078"]
    },
    "defense": {
      "applicable_categories": ["state_sponsored.China", "state_sponsored.Russia", "state_sponsored.North Korea"],
      "additional_tags": ["espionage", "ip-theft"],
      "priority_ttps": ["T1566.001", "T1574.002", "T1083", "T1041"]
    }
  },
  "geography_threat_map": {
    "Japan": {
      "apt_tags": ["targets-japan", "apt-china", "apt-north-korea"],
      "notable_groups": ["MirrorFace", "Lazarus", "Kimsuky", "APT10"]
    },
    "Southeast Asia": {
      "apt_tags": ["targets-sea", "apt-china"],
      "notable_groups": ["APT41", "Mustang Panda"]
    },
    "Europe": {
      "apt_tags": ["targets-europe", "apt-russia", "apt-china"],
      "notable_groups": ["APT28", "APT29", "APT10"]
    },
    "USA": {
      "apt_tags": ["targets-usa", "apt-china", "apt-russia", "apt-north-korea", "apt-iran"],
      "notable_groups": ["APT28", "APT29", "APT41", "Lazarus", "APT33"]
    }
  },
  "business_trigger_map": {
    "m_and_a": {
      "additional_tags": ["espionage", "insider-threat"],
      "rationale": "M&A期間中は競合・国家による情報収集活動（デューデリジェンスデータの窃取）が増加する"
    },
    "ot_connectivity": {
      "additional_tags": ["ot-targeting", "critical-infrastructure"],
      "rationale": "OT環境とIT環境の接続点はサプライチェーン攻撃のラテラルムーブ経路となる"
    },
    "cloud_migration": {
      "additional_tags": ["cloud-targeting"],
      "rationale": "移行期は設定ミスによるクラウド資産の外部露出リスクが高まる"
    },
    "ipo_or_listing": {
      "additional_tags": ["espionage", "fraud"],
      "rationale": "IPO前後は未公開の財務・戦略情報が標的になりやすい"
    },
    "supply_chain_expansion": {
      "additional_tags": ["supply-chain-attack"],
      "rationale": "新規ベンダーとの接続はサードパーティリスクを高める"
    }
  }
}
```

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
    "threat_actor_tags": ["espionage", "ip-theft", "apt-china", "targets-japan"],
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
    "threat_actor_tags": ["ransomware", "cloud-targeting", "supply-chain-attack"],
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

ただし `business_trigger_map` のトリガー（M&A, OT 接続等）が合致する場合は、スコアに関わらず `operational` 以上に自動昇格する。

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

## 8. nlink-jp ツール連携

[nlink-jp](https://github.com/nlink-jp) の既存ツールを以下の用途で流用する。

| ツール | 用途 |
|--------|------|
| `ioc-collector` | SAGE の Spanner から Observable を取得し、業種関連IOCを脅威タグ候補として活用 |
| `lite-switch` | 入力 Markdown の文章をカテゴリ分類（機密情報・財務・OT等）してElement抽出を補助 |
| `json-filter` | `business_context.json` から必要フィールドのみ抽出・検証 |

これらは**オプション統合**であり、コア機能の依存ではない。

---

## 9. ディレクトリ構成

```
BEACON/
├── high-level-design.md       # 本文書
├── pyproject.toml             # uv + ruff（pydantic, google-genai を依存に追加）
├── Makefile                   # check / generate / validate
├── src/beacon/
│   ├── config.py              # 環境変数ベース設定（GCP_PROJECT_ID, VERTEX_LOCATION 等）
│   ├── ingest/
│   │   ├── context_parser.py  # JSON/MD → BusinessContext Pydantic モデルに変換
│   │   └── schema.py          # BusinessContext / Organization / Project 等の Pydantic モデル
│   ├── analysis/
│   │   ├── element_extractor.py  # Step 1: 戦略目標・プロジェクト → 要素リスト
│   │   ├── asset_mapper.py       # Step 2: 要素 → 資産タグ（asset_tags.json 参照）
│   │   ├── threat_mapper.py      # Step 3: 資産+業種+地域 → 脅威タグ（辞書+LLM補完）
│   │   └── risk_scorer.py        # Step 4: Likelihood × Impact スコアリング
│   ├── generator/
│   │   ├── pir_builder.py        # Step 5: PIR JSON 生成（インテリジェンスレベル・有効期限自動設定）
│   │   └── report_builder.py     # collection_plan.md 生成（P3/P4 低優先度項目）
│   └── llm/
│       ├── client.py             # Vertex AI Gemini クライアント（google-genai SDK）
│       └── prompts/              # プロンプトテンプレート（src/beacon/llm/prompts/ 以下）
│           ├── context_structuring.md
│           ├── pir_generation.md
│           └── threat_tag_completion.md
├── cmd/
│   ├── generate_pir.py        # メイン CLI: context → pir_output.json
│   ├── validate_pir.py        # PIR JSON をスキーマ検証して SAGE 互換性確認
│   └── generate_schemas.py    # Pydantic から JSONSchema を自動生成
├── schema/
│   ├── business_context.schema.json   # JSONSchema for input validation
│   ├── threat_taxonomy.json           # 業種×地域×動機 → 脅威タグ辞書（MITRE ATT&CK Groups 準拠）
│   ├── asset_tags.json                # 資産種別 → SAGE タグ辞書
│   └── pir_output.schema.json         # JSONSchema for output validation
├── tests/
│   ├── fixtures/
│   │   ├── sample_context_manufacturing.json
│   │   └── sample_context_finance.md
│   └── test_*.py
└── docs/
    ├── dependencies.md
    ├── sage_integration.md      # SAGE 手動 ETL 検証手順（EN）
    └── ja/
        └── sage_integration.md  # SAGE 手動 ETL 検証手順（JA）
```

### 主要依存関係

| パッケージ | 用途 |
|-----------|------|
| `pydantic>=2.0` | BusinessContext・PIR の入出力スキーマ検証 |
| `google-genai>=1.0` | Google Gen AI SDK による Vertex AI Gemini 呼び出し |
| `structlog` | 構造化ログ（SAGE と共通） |

---

## 10. CLI インターフェース

```bash
# JSON 入力 → PIR 生成（LLMあり）＋ 収集計画も出力
uv run python cmd/generate_pir.py \
  --context sample_context.json \
  --taxonomy schema/threat_taxonomy.json \
  --output pir_output.json \
  --collection-plan collection_plan.md

# Markdown 入力 → LLMで構造化してから生成
uv run python cmd/generate_pir.py \
  --context strategy_doc.md \
  --output pir_output.json

# LLM なし（辞書のみ、エアギャップ環境向け）
uv run python cmd/generate_pir.py \
  --context sample_context.json \
  --no-llm \
  --output pir_output.json

# PIR JSON が SAGE 互換かを検証
uv run python cmd/validate_pir.py --pir pir_output.json

# Pydantic から JSONSchema を生成（schema/*.schema.json に出力）
uv run python cmd/generate_schemas.py
```

---

## 11. SAGE との連携フロー

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

## 12. 設計上のトレードオフと未解決事項

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

*実装フェーズは `TODO.md` を参照。設計変更は実装前に本文書を更新すること（RULES.md Rule 27）。*
