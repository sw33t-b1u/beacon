# BEACON — 依存パッケージ一覧

英語版（正本）: [`docs/dependencies.md`](../dependencies.md)

---

## ランタイム依存

| パッケージ | バージョン制約 | 目的 | ライセンス |
|-----------|-------------|------|---------|
| `pydantic` | `>=2.0` | BusinessContext / PIR の入出力スキーマバリデーション、`model_json_schema()` による JSONSchema 自動生成 | MIT |
| `google-genai` | `>=1.0` | Google Gen AI SDK による Vertex AI Gemini 呼び出し — Phase 2 以降で使用 | Apache-2.0 |
| `structlog` | `>=24.4.0` | 構造化ログ出力（SAGE と統一） | Apache-2.0 / MIT |
| `httpx` | `>=0.27.0` | MITRE CTI STIX バンドル取得（`cmd/update_taxonomy.py`）および SAGE Analysis API ポーリング（`src/beacon/sage/client.py`）用 HTTP クライアント | BSD-3-Clause |
| `fastapi` | `>=0.111.0` | Web UI フレームワーク — 宣言的ルーティング・OpenAPI 自動生成・Jinja2 テンプレート連携 | MIT |
| `uvicorn[standard]` | `>=0.30.0` | FastAPI 用 ASGI サーバー（`cmd/web_app.py`）。`[standard]` extras に WebSocket・HTTP/2 サポートを含む | BSD-3-Clause |
| `python-multipart` | `>=0.0.9` | FastAPI でのファイルアップロード（`POST /generate`）における multipart/form-data 解析 | Apache-2.0 |
| `jinja2` | `>=3.1.0` | Web UI 向け HTML テンプレートレンダリング（`src/beacon/web/templates/`） | BSD-3-Clause |
| `markitdown[pdf]` | `>=0.1.0` | PDF・Web 記事を Markdown に変換（`cmd/stix_from_report.py`）。pdfminer.six で PDF をサポート。ナビゲーション・フッター・広告を除去し、記事本文のみ抽出 | MIT |

---

## 開発専用依存

| パッケージ | バージョン制約 | 目的 | ライセンス |
|-----------|-------------|------|---------|
| `ruff` | `>=0.6.0` | lint + フォーマット（SAGE と統一） | MIT |
| `pytest` | `>=8.3.0` | テストフレームワーク | MIT |
| `pytest-cov` | `>=5.0.0` | カバレッジ計測 | MIT |
| `pip-audit` | `>=2.7.0` | 既知脆弱性スキャン（`make audit`、`make check` に含む） | Apache-2.0 |

---

## 選定理由

- **pydantic**: Phase 1 から型安全な入力バリデーションが必要。v2 は高速で `model_json_schema()` による JSONSchema 自動生成をサポート。
- **google-genai**: Google Gen AI SDK（`google-cloud-aiplatform` の `vertexai` サブパッケージの後継）。SAGE と同一 GCP プロジェクト内で ADC 認証を利用できるため、API キー管理が不要。`vertexai` SDK の非推奨化に伴い移行。
- **structlog**: SAGE との共有ライブラリとして採用済み。Cloud Logging 互換の JSON ログを出力。
- **httpx**: 同期・非同期の両インターフェースを統一的に扱えるモダンな HTTP クライアント。MITRE CTI STIX バンドル取得と SAGE API 呼び出しの両方で使用。`requests` と異なり同期/非同期を一元管理できる。
- **fastapi**: OpenAPI 自動生成・Pydantic v2 バリデーション・React SPA への移行パスを備えるため Web UI に採用。REST エンドポイントを HTML ルートと共存させることで将来の SPA 化を容易にしている。
- **uvicorn[standard]**: FastAPI の事実上の標準 ASGI サーバー。同じ Encode チームが開発・保守。
- **python-multipart**: FastAPI/Starlette が `multipart/form-data` ファイルアップロードを処理するために必要。
- **jinja2**: Web UI 向けの最小構成サーバーサイドテンプレート。フルスタック JS フレームワークを避け依存を軽量に保つために採用。`/api/*` エンドポイントにより将来の React 移行はサーバーサイドを変更せず実施可能。
- **markitdown[pdf]**: Microsoft のドキュメント→ Markdown 変換ツール（2024年）。pypdf + カスタム HTML ストリッパーより優れている理由：Markdown 出力は記事構造（見出し・表・リスト）を保持し、ナビゲーションバー・フッター・広告を除去するため、同じ CTI 記事でも文字数が 3〜5 倍少ない。これにより 10,000 文字のデフォルト上限でも全記事内容をカバーできる。`[pdf]` extra が pdfminer.six による PDF サポートを追加。
