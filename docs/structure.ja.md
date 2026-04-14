# BEACON — プロジェクトディレクトリ構成

このドキュメントは BEACON リポジトリのトップレベル構成を説明します。

```
BEACON/
├── src/beacon/                  # コア Python パッケージ
│   ├── config.py                # 環境変数ベースの設定 (Config dataclass)
│   ├── ingest/
│   │   ├── schema.py            # BusinessContext / CriticalAsset Pydantic モデル
│   │   ├── context_parser.py    # JSON/Markdown → BusinessContext 変換
│   │   ├── report_reader.py     # PDF / URL / テキスト → Markdown (markitdown 経由)
│   │   └── stix_extractor.py    # LLM による STIX 2.1 オブジェクト抽出
│   ├── analysis/
│   │   ├── element_extractor.py # Step 1: ビジネス要素抽出
│   │   ├── asset_mapper.py      # Step 2: 要素 → SAGE 資産タグ
│   │   ├── assets_generator.py  # CriticalAsset → SAGE 互換 assets.json
│   │   ├── threat_mapper.py     # Step 3: 業種 × 地域 → 脅威アクタータグ
│   │   └── risk_scorer.py       # Step 4: Likelihood × Impact スコアリング
│   ├── generator/
│   │   ├── pir_builder.py       # Step 5: SAGE 互換 PIR JSON 生成
│   │   └── report_builder.py    # collection_plan.md 生成 (P3/P4 項目)
│   ├── llm/
│   │   ├── client.py            # Vertex AI Gemini クライアント (google-genai SDK)
│   │   └── prompts/             # Markdown プロンプトテンプレート
│   │       ├── context_structuring.md    # context.md → BusinessContext JSON
│   │       ├── pir_generation.md         # PIR テキスト拡張
│   │       ├── threat_tag_completion.md  # LLM フォールバック脅威タグホワイトリスト
│   │       └── stix_extraction.md        # CTI レポート → STIX 2.1 オブジェクト
│   ├── review/
│   │   └── github.py            # GHE/GitHub Issue 作成（PIR レビュー用）
│   ├── sage/
│   │   └── client.py            # SAGE Analysis API クライアント
│   └── web/
│       ├── app.py               # FastAPI ルート (GET /, POST /generate, /review)
│       ├── session.py           # セッション管理 ($TMPDIR/beacon_session_*.json)
│       └── templates/           # Jinja2 HTML テンプレート (base, index, review)
│
├── cmd/                         # CLI エントリポイント（コマンドごとに1スクリプト）
│   ├── generate_pir.py          # メイン PIR パイプライン (context.md → pir_output.json)
│   ├── generate_assets.py       # CriticalAsset → SAGE assets.json
│   ├── stix_from_report.py      # PDF / URL → STIX 2.1 バンドル
│   ├── validate_pir.py          # PIR JSON SAGE 互換性検証
│   ├── generate_schemas.py      # Pydantic モデルから JSONSchema 生成
│   ├── update_taxonomy.py       # MITRE ATT&CK STIX から脅威タクソノミ同期
│   ├── submit_for_review.py     # アナリスト承認用 GHE Issue 作成
│   └── web_app.py               # Web UI 起動 (uvicorn)
│
├── schema/                      # 辞書・スキーマファイル
│   ├── threat_taxonomy.json     # 業種 × 地域 × トリガー → 脅威アクタータグ
│   ├── asset_tags.json          # 資産タイプ → SAGE タグマッピング（乗数付き）
│   ├── content_ja.json          # 日本語コンテンツ辞書
│   ├── trigger_keywords.json    # ビジネストリガーキーワードパターン
│   ├── business_context.schema.json  # BusinessContext 検証用 JSONSchema
│   └── pir_output.schema.json        # PIR 出力検証用 JSONSchema
│
├── tests/
│   ├── fixtures/                # ユニットテスト用サンプル JSON / Markdown
│   └── test_*.py                # pytest テストファイル
│
├── docs/                        # 英語ドキュメント（正本）
│   ├── setup.md                 # 前提条件、インストール、環境変数
│   ├── context_template.md      # input/context.md 用テンプレート
│   ├── data-model.md            # BusinessContext スキーマ、PIR フォーマット、LLM 統合
│   ├── dependencies.md          # サードパーティ依存関係の根拠とライセンス
│   ├── sage_integration.md      # SAGE への PIR デプロイと ETL 検証
│   ├── structure.md             # 本ファイル — ディレクトリ構成リファレンス
│   └── *.ja.md                  # 日本語翻訳（英語版と同じディレクトリに配置）
│
├── .githooks/                   # Git フック (make setup でインストール)
│   ├── pre-commit               # コミット前に make vet lint を実行
│   └── pre-push                 # プッシュ前に make check を実行
│
├── high-level-design.md         # システム設計書（正本）
├── CHANGELOG.md                 # バージョン履歴
├── Makefile                     # 品質ゲートターゲット (check, vet, lint, test, audit, setup)
├── pyproject.toml               # Python プロジェクト設定 (uv + ruff)
├── uv.lock                      # 依存関係ロックファイル
└── .env.example                 # 環境変数設定テンプレート
```

## 設計基準

- **`src/beacon/`** は再利用可能なライブラリコードをすべて格納。各サブパッケージは単一の責務を持つ。
- **`cmd/`** は引数をパースして `src/beacon/` モジュールに委譲する薄い CLI スクリプトを格納。ビジネスロジックは置かない。
- **`schema/`** はパイプラインを駆動する辞書ファイルと JSONSchema を保持。データであり、コードではない。
- **`docs/`** は利用者向けドキュメントを保持。英語版はベース名（例 `setup.md`）、日本語翻訳は `.ja.md` サフィックス（例 `setup.ja.md`）で同じディレクトリに並べて維持。
- **`high-level-design.md`** はアーキテクチャ変更前に必ず更新すること (Rule 27)。
- **`input/`** と **`output/`** はデフォルトで gitignore されるランタイムディレクトリ — 機密な運用データを含むためコミットしてはならない。
