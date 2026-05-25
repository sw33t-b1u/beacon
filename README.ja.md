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
         ├─── cmd/generate_assets.py ─── output/assets.json ─── SAGE load_assets
         │        CriticalAsset → ネットワークセグメント、
         │        アセットタグ、接続、重要度
         │
         ├─── cmd/generate_identity_assets.py ── output/identity_assets.json
         │        Identity + has_access エッジ            │
         │        (+ Initiative C Phase 2 フラグ:          ▼
         │         is_high_value_impersonation_target,    TRACE validate_identity_assets
         │         impersonation_risk_factors)            │
         │                                                 ▼
         │                                        SAGE load_identity_assets
         │
         └─── cmd/generate_user_accounts.py ──── output/user_accounts.json
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
| [docs/setup.ja.md](docs/setup.ja.md) | 前提条件・インストール・環境変数・GCP 認証 |
| [docs/context_template.ja.md](docs/context_template.ja.md) | `input/context.md` テンプレート — パイプライン入力となる Markdown 戦略ドキュメントの記述ガイド |
| [docs/data-model.ja.md](docs/data-model.ja.md) | BusinessContext スキーマ・PIR 出力フォーマット・`identity_assets.json` / `user_accounts.json` スキーマ・インテリジェンスレベル・脅威タクソノミー |
| [docs/sage_integration.ja.md](docs/sage_integration.ja.md) | SAGE への PIR デプロイと ETL 検証手順 |
| [docs/dependencies.ja.md](docs/dependencies.ja.md) | 依存パッケージの選定理由とライセンス情報 |

## ストレージバックエンド（Initiative I）

BEACON 1.1.0 は成果物の永続化を抽象化する **StorageBackend** を導入しました。生成された
すべての成果物（`pir_output.json`・`assets.json`・STIX バンドルなど）は `output/` への
直接書き込みではなく、プラガブルなバックエンドを経由して保存されます。

| バックエンド | 説明 | 有効化 |
|-------------|------|--------|
| `local`（デフォルト） | ローカルディレクトリに書き込む | `BEACON_STORAGE=local` |
| `gcs` | Google Cloud Storage に書き込む | `BEACON_STORAGE=gcs` |

**環境変数:**

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `BEACON_STORAGE` | `local` | ストレージバックエンド: `local` または `gcs` |
| `BEACON_STORAGE_BASE_DIR` | `output/` | `local` バックエンドのベースディレクトリ |
| `BEACON_GCS_BUCKET` | — | GCS バケット名（`gcs` バックエンドで必須） |
| `BEACON_GCS_PREFIX` | `beacon/` | GCS バケット内のキープレフィックス |

GCS サポートにはオプションインストールが必要です:

```bash
uv sync --extra gcs
```

成果物のファイル名は `<type>_<YYYYMMDDHHmm>.json` 形式
（例: `pir_202506011430.json`）。カテゴリ: `pir`・`assets`・`stix`・`plans`・`crawl_state`。

## Web ダッシュボード（Initiative I）

Web UI（`uv run beacon web`、デフォルト `http://localhost:8000`）が
**5 タブダッシュボード**として統合されました:

| タブ | 用途 |
|------|------|
| **Dashboard** | パイプラインサマリ: PIR 件数・収集状況・チョークポイント |
| **PIR** | PIR 生成・出力レビュー・StorageBackend からの過去実行自動ロード |
| **Collection** | TRACE の `crawl-single` / `crawl-batch` をサブプロセスで実行 |
| **Threats** | SAGE API プロキシ: アクター検索・TTP ルックアップ・脅威サマリ |
| **Settings** | ストレージモード・SAGE URL・TRACE パスの設定。`.beacon_settings.json` に永続化 |

設定の優先順位: **環境変数 > `.beacon_settings.json` > デフォルト値**

> **非推奨化（BEACON 1.1.0）:** `cmd/submit_for_review.py`（GHE Issue 作成）は非推奨となり、
> 将来のリリースで削除予定です。Web ダッシュボードの **Settings タブ** が GHE 承認ワークフロー
> をブラウザ内承認フローに置き換えます。Collection タブが TRACE を呼び出せるよう
> `TRACE_ROOT_PATH` を設定してください。

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
