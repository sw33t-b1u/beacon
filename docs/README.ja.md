# BEACON ドキュメント

## オペレーター向け（デプロイ・運用）

| ドキュメント | 説明 |
|------------|------|
| [setup.md](setup.md) | 環境構築、GCP デプロイ、Cloud Run |
| [operations.md](operations.md) | 日常運用、MISP キャッシュ更新、SAGE 連携 |

## アナリスト向け（日常利用）

| ドキュメント | 説明 |
|------------|------|
| [triggers.md](triggers.md) | ビジネストリガーの定義と設定 |
| コンテキストテンプレート | [`schema/context_template.md`](../schema/context_template.md) — セキュリティコンテキスト入力テンプレート |

## 開発者向け（コード貢献）

| ドキュメント | 説明 |
|------------|------|
| [structure.md](structure.md) | プロジェクトのディレクトリ構成 |
| [data-model.md](data-model.md) | PIR 出力スキーマ、スコア内訳、アクタートリアージモデル |
| [dependencies.md](dependencies.md) | サードパーティ依存関係の根拠 |

## アーキテクト向け（設計判断）

| ドキュメント | 説明 |
|------------|------|
| [api-stability.md](api-stability.md) | API 安定性ポリシーおよび後方互換性保証 |
| [high-level-design.md](high-level-design.md) | システム設計（ローカルのみ、gitignored） |
| [citations.md](citations.md) | 外部引用とライセンス一覧 |

## クロスプロジェクト（シンボリックリンク経由で共有）

| ドキュメント | 正規リポジトリ | 説明 |
|------------|--------------|------|
| [pipeline-guide.md](pipeline-guide.md) | BEACON | CTI パイプラインのエンドツーエンド運用 |

> IR フィードバックフローの計算式は [SAGE docs/ir-feedback-flow.md](../../sage/docs/ir-feedback-flow.md) を参照。

日本語版は各ファイルの `.ja.md` サフィックスで同ディレクトリに配置。
