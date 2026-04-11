# BEACON

**Business Environment Assessment for CTI Organizational Needs**

BEACON は組織のビジネスコンテキスト（JSON またはマークダウン形式の戦略ドキュメント）を、辞書ベースのパイプラインと Google Gen AI（Gemini）を組み合わせて [SAGE](https://github.com/sw33t-b1u/sage) 互換の **優先情報要件（PIR）JSON** に変換します。

[English README](README.md)

> PIR とは「セキュリティがビジネスを守るために必要な情報要件」です。BEACON はビジネス戦略と CTI 優先順位付けの橋渡し役を担います。

## 概要

BEACON は同一のコンテキストドキュメントから 3 つの出力パイプラインを提供します：

```
  input/context.md  (または .json)
         │
         ├─── cmd/generate_pir.py ──────────────────────────────────────────┐
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
         └─── cmd/generate_assets.py ─── output/assets.json ─── SAGE load_assets
                  CriticalAsset → ネットワークセグメント、
                  アセットタグ、接続、重要度


  PDF / Web 記事
         │
         └─── cmd/stix_from_report.py ── output/stix_bundle.json ─── SAGE ETL
                  markitdown → クリーン Markdown → Gemini → STIX 2.1
                  （intrusion-set, attack-pattern, malware, vulnerability …）
```

**モード:**

| モード | 入力 | LLM | ユースケース |
|--------|------|-----|------------|
| `--no-llm` | JSON のみ | なし | エアギャップ環境 / コスト制限 |
| デフォルト | JSON または Markdown | Gemini（Vertex AI） | フル品質 PIR + アセット |
| `stix_from_report` | PDF または URL | Gemini（Vertex AI） | CTI レポート → STIX バンドル |

## ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [docs/ja/setup.md](docs/ja/setup.md) | 前提条件・インストール・環境変数・GCP 認証 |
| [docs/ja/context_template.md](docs/ja/context_template.md) | `input/context.md` テンプレート — パイプライン入力となる Markdown 戦略ドキュメントの記述ガイド |
| [docs/ja/data-model.md](docs/ja/data-model.md) | BusinessContext スキーマ・PIR 出力フォーマット・インテリジェンスレベル・脅威タクソノミー |
| [docs/ja/sage_integration.md](docs/ja/sage_integration.md) | SAGE への PIR デプロイと ETL 検証手順 |
| [docs/ja/dependencies.md](docs/ja/dependencies.md) | 依存パッケージの選定理由とライセンス情報 |

## クイックスタート

```bash
cd BEACON
uv sync --extra dev
make setup             # Git フックをインストール
cp .env.example .env   # GCP_PROJECT_ID などの変数を入力
```

詳細なセットアップ手順は [docs/ja/setup.md](docs/ja/setup.md) を参照。

## ディレクトリ構成

```
BEACON/
├── pyproject.toml
├── Makefile
├── .env.example
├── input/              # context.md を置くディレクトリ（gitignore 対象 — 機密データ）
├── output/             # 生成ファイル: pir_output.json, collection_plan.md（gitignore 対象）
├── src/beacon/
│   ├── config.py
│   ├── ingest/{schema,context_parser,report_reader,stix_extractor}.py
│   ├── analysis/{element_extractor,asset_mapper,assets_generator,threat_mapper,risk_scorer}.py
│   ├── generator/{pir_builder,report_builder}.py
│   ├── llm/{client,prompts/}
│   ├── review/github.py
│   ├── sage/client.py
│   └── web/{app,session,templates/}
├── cmd/
│   ├── generate_pir.py
│   ├── generate_assets.py
│   ├── stix_from_report.py
│   ├── validate_pir.py
│   ├── generate_schemas.py
│   ├── update_taxonomy.py
│   ├── submit_for_review.py
│   └── web_app.py
├── schema/
│   ├── threat_taxonomy.json
│   ├── asset_tags.json
│   ├── content_ja.json
│   └── trigger_keywords.json
└── tests/
    ├── fixtures/
    └── test_*.py
```

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

## ライセンス

Apache-2.0 — [LICENSE](LICENSE) を参照
