# BEACON

**Business Environment Assessment for CTI Organizational Needs**

BEACON は組織のビジネスコンテキスト（JSON またはマークダウン形式の戦略ドキュメント）を、辞書ベースのパイプラインと Vertex AI Gemini を組み合わせて [SAGE](../SAGE) 互換の **優先情報要件（PIR）JSON** に変換します。

> PIR とは「セキュリティがビジネスを守るために必要な情報要件」です。BEACON はビジネス戦略と CTI 優先順位付けの橋渡し役を担います。

英語版（正本）: [`README.md`](README.md)

---

## 概要

```
[business_context.json / strategy.md]
            │
            ▼
     BEACON PIPELINE
  ┌──────────────────────┐
  │ Step 1: 要素抽出     │  戦略目標・プロジェクト・クラウンジュエル
  │ Step 2: アセットマップ│  → SAGE アセットタグ（plm, ot, cloud, erp …）
  │ Step 3: 脅威マップ   │  業種 × 地理 → 脅威アクタータグ
  │ Step 4: リスクスコア │  可能性 × 影響（1〜5 スケール）
  │ Step 5: PIR 構築     │  SAGE 互換 PIR JSON
  └──────────────────────┘
            │
            ▼
    [pir_output.json]  →  SAGE ETL  →  pir_adjusted_criticality
```

**2 つのモード:**

| モード | 入力 | LLM | ユースケース |
|--------|------|-----|------------|
| `--no-llm` | JSON のみ | なし | エアギャップ環境 / コスト制限 |
| デフォルト | JSON または Markdown | Vertex AI Gemini | フル品質 |

---

## クイックスタート

### 前提条件

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) パッケージマネージャー
- Vertex AI API を有効化した GCP プロジェクト（LLM モード使用時）

### セットアップ

```bash
cd BEACON
uv sync
```

### PIR 生成（辞書のみモード）

```bash
uv run python -m cmd.generate_pir \
  --context tests/fixtures/sample_context_manufacturing.json \
  --no-llm \
  --output pir_output.json
```

### PIR 生成（Vertex AI 使用）

```bash
export GCP_PROJECT_ID=your-project-id

uv run python -m cmd.generate_pir \
  --context tests/fixtures/sample_context_manufacturing.json \
  --output pir_output.json
```

### Markdown 入力の解析

```bash
uv run python -m cmd.generate_pir \
  --context strategy_doc.md \
  --output pir_output.json
```

### SAGE 互換性の検証

```bash
uv run python -m cmd.validate_pir --pir pir_output.json
```

---

## 入力: BusinessContext JSON

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
  "supply_chain": {
    "ot_connectivity": true,
    "cloud_providers": ["GCP"]
  }
}
```

完全なスキーマ: `schema/business_context.schema.json`（`uv run python -m cmd.generate_schemas` で生成）

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
    "collection_focus": ["MirrorFace / APT10 の新規TTP観測", "OT/ICS環境を標的とする脆弱性悪用情報"],
    "valid_from": "2026-04-04",
    "valid_until": "2027-04-04",
    "risk_score": { "likelihood": 5, "impact": 5, "composite": 25 }
  }
]
```

出力されるのは P1（composite ≥ 20）と P2（composite ≥ 12）のみです。低優先度の項目は `collection_plan.md`（Phase 3）に記録されます。

---

## インテリジェンスレベルと有効期間

| レベル | composite | valid_until | 例 |
|--------|-----------|-------------|-----|
| `strategic` | 20〜25 | +12 ヶ月 | 業種 IP を標的とする国家支援型 APT |
| `operational` | 12〜19 | +6 ヶ月 | 進行中のランサムウェアキャンペーン |
| `tactical` | 1〜11 | +1 ヶ月 | 特定 CVE の悪用 |

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

### 環境変数

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `GCP_PROJECT_ID` | — | GCP プロジェクト（SAGE と共有） |
| `VERTEX_LOCATION` | `us-central1` | Vertex AI リージョン |
| `BEACON_LLM_SIMPLE` | `gemini-2.5-flash-lite` | 単純タスク用モデル |
| `BEACON_LLM_MEDIUM` | `gemini-2.5-flash` | 中程度タスク用モデル |
| `BEACON_LLM_COMPLEX` | `gemini-2.5-pro` | 複雑な推論用モデル |

---

## プロジェクト構成

```
BEACON/
├── pyproject.toml             # uv + ruff
├── Makefile                   # check / generate / validate / test / audit
├── CHANGELOG.md
├── src/beacon/
│   ├── config.py
│   ├── ingest/
│   │   ├── schema.py          # BusinessContext Pydantic モデル
│   │   └── context_parser.py  # JSON / Markdown パーサー
│   ├── analysis/
│   │   ├── element_extractor.py  # Step 1
│   │   ├── asset_mapper.py       # Step 2
│   │   ├── threat_mapper.py      # Step 3
│   │   └── risk_scorer.py        # Step 4
│   ├── generator/
│   │   ├── pir_builder.py        # Step 5
│   │   └── report_builder.py     # collection_plan.md（Phase 3）
│   └── llm/
│       ├── client.py
│       └── prompts/
│           ├── context_structuring.md
│           ├── pir_generation.md
│           └── threat_tag_completion.md
├── cmd/
│   ├── generate_pir.py
│   ├── validate_pir.py
│   └── generate_schemas.py
├── schema/
│   ├── threat_taxonomy.json
│   ├── asset_tags.json
│   ├── business_context.schema.json  （生成ファイル）
│   └── pir_output.schema.json        （生成ファイル）
├── tests/
│   ├── fixtures/
│   │   ├── sample_context_manufacturing.json
│   │   └── sample_context_finance.md
│   └── test_*.py              # SAGE 依存なし
└── docs/
    ├── dependencies.md
    ├── sage_integration.md    # SAGE ETL 連携手順（英語版）
    └── ja/
        └── sage_integration.md  # SAGE ETL 連携手順（日本語版）
```

---

## 開発

```bash
# 品質ゲート（lint + test、インテグレーションテストを除く）
make check

# テストのみ実行
make test

# インテグレーションテスト実行（GCP_PROJECT_ID 必須）
make test-integration

# セキュリティ監査
make audit

# Pydantic モデルから JSON スキーマを生成
uv run python cmd/generate_schemas.py
```

### テストスイート概要

| テストファイル | カバー範囲 | SAGE 必須? |
|--------------|----------|-----------|
| `test_element_extractor.py` | Step 1: 要素抽出 | 不要 |
| `test_threat_mapper.py` | Step 3: 脅威マッピング（辞書） | 不要 |
| `test_risk_scorer.py` | Step 4: リスクスコアリング | 不要 |
| `test_pir_builder.py` | Step 5: PIR JSON 生成 | 不要 |
| `test_report_builder.py` | collection_plan.md 生成 | 不要 |
| `test_sage_compatibility.py` | SAGE PIRFilter 向け PIR フィールド契約 | 不要 |
| `test_context_parser_md.py` | Markdown → BusinessContext（LLM モック） | 不要 |
| `test_llm_client.py` | Vertex AI クライアント（モック） | 不要 |

`test_sage_compatibility.py` は PIR フィールド契約をインラインで検証します。SAGE リポジトリは**テスト実行に不要**です。

---

## SAGE との連携

```
[アナリスト]
    │  business_context.json の作成・更新
    ▼
[BEACON: generate_pir]
    │  pir_output.json
    ▼
[アナリストレビュー]
    │  PIR 内容の確認・編集
    ▼
[SAGE PIR_FILE_PATH へ配置]
    │  cp pir_output.json /config/pir.json
    ▼
[SAGE ETL]
    │  Targets エッジ + pir_adjusted_criticality 更新
    ▼
[SAGE Analysis API]
    │  チョークポイント / 攻撃パスクエリに PIR ウェイトが反映
```

推奨更新頻度: 四半期ごと、または組織に重大な変化（M&A、新規プロジェクト、OT 拡張）があった場合。

---

## 脅威タクソノミーカバレッジ

`schema/threat_taxonomy.json`（MITRE ATT&CK Groups v15 ベース）:

| カテゴリ | グループ |
|---------|---------|
| 中国（国家） | APT10, APT41, MirrorFace, Mustang Panda |
| ロシア（国家） | APT28, APT29, Sandworm |
| 北朝鮮（国家） | Lazarus, Kimsuky, APT38 |
| イラン（国家） | APT33, APT34, MuddyWater |
| ランサムウェア | LockBit, RansomHub, BlackCat, Cl0p |
| ハクティビスト | （タグベース、名称なしグループ） |

対応業種: 製造業、金融、エネルギー、医療、防衛、テクノロジー、物流、政府、教育。
