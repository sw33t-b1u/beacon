# BEACON

**Business Environment Assessment for CTI Organizational Needs**

BEACON は組織のビジネスコンテキスト（JSON またはマークダウン形式の戦略ドキュメント）を、辞書ベースのパイプラインと Google Gen AI（Gemini）を組み合わせて [SAGE](https://github.com/sw33t-b1u/sage) 互換の **優先情報要件（PIR）JSON** に変換します。

[English README](README.md)

> PIR とは「セキュリティがビジネスを守るために必要な情報要件」です。BEACON はビジネス戦略と CTI 優先順位付けの橋渡し役を担います。

## 概要

BEACON は同一のコンテキストドキュメントから 4 つの出力パイプラインを提供します：

```
  input/context.md  (または .json)
         │
         ├─── beacon pir-generate ──────────────────────────────────────────┐
         │                                                                   │
         │    ┌──────────────────────┐                                       │
         │    │ Step 1: 要素抽出     │  目標・クラウンジュエル・アセット     │
         │    │ Step 2: アセットマップ│  → SAGE タグ（plm, ot, erp …）      │
         │    │ Step 3: 脅威マップ   │  業種 × 地理 → アクタータグ          │
         │    │ Step 4: リスクスコア │  可能性 × 影響（1〜5）               │
         │    │ Step 5: PIR 構築     │  SAGE 互換 PIR JSON                  │
         │    └──────────────────────┘                                       │
         │                        output/pir_output.json ────────────────────┘
         │                                  │                        │
         │                                  ▼                        ▼
         │                           SAGE ETL             pir_adjusted_criticality
         │
         ├─── beacon assets-generate ─── output/assets.json ─── SAGE load_assets
         │        CriticalAsset → ネットワークセグメント、
         │        アセットタグ、接続、重要度
         │
         ├─── beacon identity-generate ── output/identity_assets.json
         │        Identity + has_access エッジ            │
         │        (+ Initiative C Phase 2 フラグ:          ▼
         │         is_high_value_impersonation_target,    TRACE validate_identity_assets
         │         impersonation_risk_factors)            │
         │                                                 ▼
         │                                        SAGE load_identity_assets
         │
         └─── beacon accounts-generate ──── output/user_accounts.json
                  UserAccount + account_on_asset エッジ  │
                                                          ▼
                                               TRACE validate_user_accounts
                                                          │
                                                          ▼
                                               SAGE load_user_accounts
```

> **CTI レポート取り込み（PDF / URL → STIX 2.1）は BEACON 0.9.0 で姉妹プロジェクト
> [TRACE](../TRACE/) に移管された。** 削除された `BEACON/cmd/stix_from_report.py` の
> 代わりに `TRACE/cmd/crawl_single.py` を使うこと。

**モード:**

| モード | 入力 | LLM | ユースケース |
|--------|------|-----|------------|
| `--no-llm` | JSON のみ | なし | エアギャップ環境 / コスト制限 |
| デフォルト | JSON または Markdown | Gemini（Vertex AI） | フル品質 PIR + アセット |

## ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [docs/setup.ja.md](docs/setup.ja.md) | クローン、インストール、設定、テスト、初回実行 |
| [docs/deploy.ja.md](docs/deploy.ja.md) | Cloud Run デプロイ |
| [docs/usage.ja.md](docs/usage.ja.md) | Web ダッシュボード、CLI、ワークフロー、運用 |
| [docs/pipeline-guide.ja.md](docs/pipeline-guide.ja.md) | エンドツーエンド CTI パイプライン（BEACON → TRACE → SAGE） |
| [docs/data-model.ja.md](docs/data-model.ja.md) | PIR 出力スキーマ、スコア内訳、アクタートリアージモデル |
| [docs/structure.ja.md](docs/structure.ja.md) | プロジェクトのディレクトリ構成 |
| [docs/dependencies.ja.md](docs/dependencies.ja.md) | 依存パッケージの選定理由とライセンス情報 |
| [docs/api-stability.ja.md](docs/api-stability.ja.md) | API 安定性ポリシーおよび後方互換性保証 |
| [docs/citations.ja.md](docs/citations.ja.md) | 外部引用とライセンス一覧 |
| [schema/context_template.ja.md](schema/context_template.ja.md) | ビジネスコンテキスト入力テンプレート |
| [schema/triggers.md](schema/triggers.md) | ビジネストリガーの定義（英語正本） |

クロスプロジェクト:
- [SAGE ir-feedback-flow.md](https://github.com/sw33t-b1u/sage/blob/main/docs/ir-feedback-flow.md) — IR フィードバックループとスコアリング計算式

## クイックスタート

```bash
cd BEACON
uv sync --extra dev
make setup             # Git フックをインストール
cp .env.example .env   # GCP_PROJECT_ID などの変数を入力
```

詳細なセットアップ手順は [docs/setup.ja.md](docs/setup.ja.md) を参照。

## ディレクトリ構成

詳細なディレクトリレイアウトと設計方針は [docs/structure.ja.md](docs/structure.ja.md) を参照。

## 開発

```bash
make setup     # Git フックをインストール（クローン後に一度実行）
make check     # lint + test + audit（フル品質ゲート）
make vet       # ruff check
make lint      # ruff format --check
make format    # ruff format + fix
make test      # pytest（ユニットテスト）
make audit     # pip-audit
```

## PIR 方法論の参考資料

BEACON の PIR 生成は以下の CTI 方法論に準拠しています:

- [FIRST CTI-SIG — Priority Intelligence Requirements カリキュラム](https://www.first.org/global/sigs/cti/curriculum/pir)
- [SANS — Bridging Gaps in CTI: A Practical Guide to Threat-Informed Security PIRs](https://www.sans.org/blog/bridging-gaps-cti-practical-guide-threat-informed-security-pirs)

採用している主な指針: 1 つの PIR = 1 つの意思決定ポイント、"Less is more"（1 回の実行で最大 5 件）、Strategic PIR → Operational TAP → Tactical PTTP のカスケード。詳細は `src/beacon/analysis/pir_clusterer.py` を参照。

## ライセンス

Apache-2.0 — [LICENSE](LICENSE) を参照
