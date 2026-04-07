# BEACON — データモデル

英語版（正本）: [`docs/data-model.md`](../data-model.md)

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

脅威タクソノミーを MITRE ATT&CK から更新:

```bash
uv run python cmd/update_taxonomy.py [--dry-run]
```
