# BEACON — TODO / 未解決事項

## 設計上の未解決事項（要確認）

| # | 項目 | 状態 |
|---|------|------|
| D-1 | `threat_taxonomy.json` の初期辞書作成：MITRE ATT&CK Groups を起点に Big 4 + ランサムウェア を優先実装 | ✅ 完了 |
| D-2 | `VERTEX_LOCATION` のデフォルトを `us-central1` にする。変更は環境変数 `VERTEX_LOCATION` で対応 | ✅ 確認済み |
| D-3 | `gemini-2.5-pro` のコストは許容範囲。辞書根拠なし時のみ呼び出す実装で問題なし | ✅ 確認済み |
| D-4 | `--no-llm` 時の Markdown 入力: `parse_markdown()` スタブを `context_parser.py` に置き、`NotImplementedError` を送出。Phase 2 で実装 | ✅ 確認済み |
| D-5 | Pydantic v2 バリデーションは型・必須フィールド・Literal 制約のみ。クロスフィールド検証は Phase 3 (SAGE 連携) 時に追加 | ✅ 確認済み |

---

## 実装フェーズ

| フェーズ | 内容 | 成果物 | 状態 |
|--------|------|--------|------|
| Phase 1 | プロジェクト基盤 + 入力スキーマ + 辞書ベースPIR生成 | `--no-llm` で動くCLI | ✅ 完了 |
| Phase 2 | Vertex AI Gemini 統合 + LLM補完パイプライン | Markdown入力対応・PIR品質向上 | ✅ 完了 |
| Phase 3 | レポート・収集計画生成 + SAGE連携検証 | `collection_plan.md` | ✅ 完了 |
| Phase 4 | MITRE 自動更新 + GHE レビュー + SAGE API 連携 + Web UI | 全機能統合 | ✅ 完了 |

---

## Phase 1 タスク

### P1-1: プロジェクト基盤 ✅

- [x] `pyproject.toml` を作成（`pydantic>=2.0`, `structlog`, `google-cloud-aiplatform>=1.60`）
- [x] `Makefile` を作成（`check` / `generate` / `validate` ターゲット）
- [x] `src/beacon/config.py` を作成
  - `GCP_PROJECT_ID`, `VERTEX_LOCATION`（デフォルト: `us-central1`）
  - `BEACON_LLM_SIMPLE`（デフォルト: `gemini-2.5-flash-lite`）
  - `BEACON_LLM_MEDIUM`（デフォルト: `gemini-2.5-flash`）
  - `BEACON_LLM_COMPLEX`（デフォルト: `gemini-2.5-pro`）

### P1-2: 入力スキーマ（Pydantic）✅

- [x] `src/beacon/ingest/schema.py` を作成
  - `Organization`, `StrategicObjective`, `Project`, `CrownJewel`, `SupplyChain`, `BusinessContext`
  - `Literal` 型で `industry`, `sensitivity`, `business_impact` を制約
- [x] `src/beacon/ingest/context_parser.py` を作成
  - JSON 入力 → `BusinessContext` の parse と validate
  - Markdown 入力 → `NotImplementedError` スタブ（Phase 2 で実装）
- [x] `schema/business_context.schema.json` を作成（`cmd/generate_schemas.py` で生成）

### P1-3: 辞書ファイル作成 ✅

- [x] `schema/threat_taxonomy.json` を作成
  - Big 4（中国・ロシア・北朝鮮・イラン）+ ランサムウェア + ハクティビスト
  - MITRE ATT&CK Groups データ（v15）を参照して `mitre_groups` / `priority_ttps` を入力
  - 業種マップ（manufacturing, finance, energy, healthcare, defense, technology, logistics, government, education）
  - 地域マップ（Japan, Southeast Asia, South Korea, Europe, USA, Middle East）
  - ビジネストリガーマップ（m_and_a, ot_connectivity, cloud_migration, ipo_or_listing, supply_chain_expansion）
- [x] `schema/asset_tags.json` を作成
  - 資産種別（plm, erp, ot, cloud, external-facing, backup, identity, financial, hr, r_and_d, supply_chain）→ SAGE 資産タグのマッピング
  - `criticality_multiplier` の初期値を定義

### P1-4: パイプライン実装（Step 1〜5、辞書のみ）✅

- [x] `src/beacon/analysis/element_extractor.py` — Step 1
- [x] `src/beacon/analysis/asset_mapper.py` — Step 2
- [x] `src/beacon/analysis/threat_mapper.py` — Step 3（辞書マッチのみ）
- [x] `src/beacon/analysis/risk_scorer.py` — Step 4
- [x] `src/beacon/generator/pir_builder.py` — Step 5

### P1-5: CLI と検証 ✅

- [x] `cmd/generate_pir.py` — メイン CLI（`--context`, `--taxonomy`, `--output`, `--no-llm`）
- [x] `cmd/validate_pir.py` — PIR JSON をスキーマ検証
- [x] `cmd/generate_schemas.py` — JSONSchema を Pydantic から自動生成
- [x] `schema/pir_output.schema.json` / `schema/business_context.schema.json` — `generate_schemas.py` 実行で生成

### P1-6: テスト ✅

- [x] `tests/fixtures/sample_context_manufacturing.json` を作成（製造業×日本×OT接続）
- [x] `tests/test_element_extractor.py`（15テスト）
- [x] `tests/test_threat_mapper.py`（13テスト）
- [x] `tests/test_risk_scorer.py`（12テスト）
- [x] `tests/test_pir_builder.py`（16テスト）
- 合計 56テスト all pass / lint clean

---

## Phase 2 タスク

**設計決定（確認済み）:**
- MD→JSON変換: ワンショット（全文を1回のLLM呼び出しで変換）
- PIR文章生成: Phase 1の辞書ベース結果をコンテキストとしてLLMに渡し、description/rationale/collection_focusを拡充（上書きではなく拡充）
- テスト戦略: `unittest.mock` でモック（`make check` 対象）+ `@pytest.mark.integration` で実APIテストを分離（`make test-integration` で実行）

### P2-1: Vertex AI LLM クライアント ✅

- [x] `src/beacon/llm/client.py` を作成（モジュールレベル import + `call_llm` / `call_llm_json` 公開）
- [x] `src/beacon/llm/prompts/context_structuring.md`
- [x] `src/beacon/llm/prompts/pir_generation.md`
- [x] `src/beacon/llm/prompts/threat_tag_completion.md`

### P2-2: LLM 統合 ✅

- [x] `ingest/context_parser.py` の Markdown パスを実装（ワンショット / `gemini-2.5-flash-lite`）
- [x] `analysis/threat_mapper.py` に LLM フォールバック追加（`use_llm=True` + 辞書ミスマッチ時のみ）
- [x] `generator/pir_builder.py` に LLM 文章拡充を統合（`use_llm=True` / `gemini-2.5-flash`）
- [x] `analysis/risk_scorer.py` に LLM 判断補助を追加（`use_llm=True` + 辞書根拠なし時のみ / `gemini-2.5-pro`）

### P2-3: テスト ✅

- [x] `pyproject.toml` に `integration` marker 追加、`Makefile` に `test-integration` ターゲット追加
- [x] `tests/fixtures/sample_context_finance.md` を作成
- [x] `tests/test_llm_client.py`（15テスト / モック + `@pytest.mark.integration`）
- [x] `tests/test_context_parser_md.py`（8テスト / モック + `@pytest.mark.integration`）
- 合計 74テスト all pass / lint clean（統合テスト 2件 deselected）

---

## Phase 3 タスク

**設計決定（確認済み）:**
- `report_builder.py` は `collection_plan.md` 生成のみ（P3/P4 低優先度項目の収集計画一覧）。PIR の `description`/`rationale` は `pir_builder.py` が担うため重複しない
- SAGE 連携検証: Spanner 実環境なしで実施できるスキーマ静的検証（pytest）を採用。手動 ETL 検証手順は `docs/sage_integration.md` に記載

### P3-1: 収集計画生成 ✅

- [x] `src/beacon/generator/report_builder.py` を作成
  - P3/P4 スコア（composite < 12）の低優先度項目を `collection_plan.md` として出力
  - 各項目に業種・脅威タグ・推奨収集ソースを記載
  - ビジネストリガー別収集アクション・収集頻度テーブルを含む
- [x] `cmd/generate_pir.py` に `--collection-plan FILE` オプションを追加
- [x] `tests/test_report_builder.py`（13テスト）

### P3-2: SAGE 連携検証 ✅

- [x] SAGE の `src/sage/pir/filter.py` を読み込み、PIR JSON に必要なフィールド要件を確認
- [x] `tests/test_sage_compatibility.py` を作成（スキーマ静的検証 / Spanner 不要）
  - `pir_id`, `threat_actor_tags`, `asset_weight_rules[].tag`, `asset_weight_rules[].criticality_multiplier` の形式確認
  - `valid_from` / `valid_until` が ISO 日付文字列であることを確認
  - `PIRFilter` との実動作確認（`is_relevant_actor`, `adjust_asset_criticality`, `build_targets`）→ SAGE 非依存の `TestSAGEContractValidation` に置き換え済み
- [x] `docs/sage_integration.md` を作成（手動 ETL 検証手順）
  - `pir_output.json` を `PIR_FILE_PATH` に配置する手順
  - `make run-etl` 実行と `pir_adjusted_criticality` 確認クエリを記載
- [x] スキーマ不整合なし（`pir_output.schema.json` 修正不要）
- 合計 119テスト all pass / lint clean（別リポジトリ対応完了: `conftest.py` 削除・`TestSAGEContractValidation` に置き換え）

---

## Phase 4 タスク

**設計決定（確認済み）:**
- 4-1 MITRE ATT&CK 自動更新: `cmd/update_taxonomy.py` — MITRE CTI GitHub から STIX バンドルを取得し `threat_taxonomy.json` を更新
- 4-2 PIR レビューワークフロー: 専用コマンド `cmd/submit_for_review.py` — `generate_pir.py` とは独立して GHE Issue を作成
- 4-3 SAGE Spanner 参照: SAGE Analysis API 経由（`SAGE_API_URL` 環境変数）— Spanner に直接依存しない疎結合設計
- 4-4 Web UI: FastAPI + Jinja2 — 依存最小・Python のみ。利用者増加時に React SPA へ移行検討（API 構造は共通化しておく）

### P4-1: MITRE ATT&CK 自動更新 ✅

**目的:** MITRE CTI GitHub の最新 ATT&CK STIX バンドルを取得して `schema/threat_taxonomy.json` の `mitre_groups` と `priority_ttps` を自動更新する。`geography_threat_map` / `business_trigger_map` / `industry_threat_map` は手動管理のため上書きしない。

**追加依存:** `httpx`（`pyproject.toml` の `dependencies` に追加）

**作成ファイル:**
- `cmd/update_taxonomy.py` — CLI エントリポイント

**`cmd/update_taxonomy.py` 仕様:**
```
uv run python cmd/update_taxonomy.py [--output schema/threat_taxonomy.json] [--dry-run]
```
- `--dry-run`: taxonomy.json を上書きせず差分を stdout に出力
- 取得元: `https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json`
- STIX `type=intrusion-set` → グループ名・エイリアス → `actor_categories` の各 actor の `mitre_groups` と照合して更新
- STIX `type=attack-pattern` → technique ID（T番号）→ `priority_ttps` リストを更新
- 既存エントリの手動追加タグ（`tags`, `target_geographies` 等）は保持する

**テスト:**
- `tests/test_update_taxonomy.py`
  - HTTP リクエストを `unittest.mock` でモック（小さなサンプル STIX バンドルを fixture に置く）
  - `--dry-run` が taxonomy.json を変更しないことを確認
  - 既存の手動タグが保持されることを確認
  - `mitre_groups` が新しいグループで更新されることを確認

---

### P4-2: PIR レビューワークフロー (GHE) ✅

**目的:** 生成済み `pir_output.json` を GitHub Enterprise の Issue としてアナリストに投稿し、コメントによる承認フローを実現する。`generate_pir.py` とは独立したコマンドとして提供。

**環境変数（`config.py` に追加）:**
| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `GHE_TOKEN` | — | GitHub / GHE Personal Access Token |
| `GHE_REPO` | — | `owner/repo` 形式 |
| `GHE_API_BASE` | `https://api.github.com` | セルフホスト GHE は上書き |

**作成ファイル:**
- `src/beacon/review/github.py` — GHE Issue 作成クライアント
- `cmd/submit_for_review.py` — CLI エントリポイント

**`cmd/submit_for_review.py` 仕様:**
```
uv run python cmd/submit_for_review.py --pir pir_output.json [--collection-plan collection_plan.md]
```
- `pir_output.json` を読み込み、各 PIR について GHE Issue を作成
- Issue タイトル: `[PIR Review] PIR-YYYY-NNN — <intelligence_level>`
- Issue 本文（Markdown）:
  ```
  ## PIR Review Request
  **Generated:** YYYY-MM-DD | **Valid Until:** YYYY-MM-DD
  **Risk Score:** L=N, I=N, Composite=NN

  ### Description
  <description>

  ### Rationale
  <rationale>

  ### Threat Actor Tags
  `tag1` `tag2` ...

  ### Asset Weight Rules
  | Tag | Multiplier |
  |-----|-----------|
  | plm | 2.5       |

  ### Collection Focus
  - item1
  - item2

  ## Review Checklist
  - [ ] Description is accurate
  - [ ] Threat actor tags are appropriate
  - [ ] Asset weight rules are correct
  - [ ] Approved for SAGE deployment
  ```
- `--collection-plan` 指定時は Issue にコメントとして添付

**テスト:**
- `tests/test_github_review.py`
  - GHE API (`POST /repos/{owner}/{repo}/issues`) を `unittest.mock` でモック
  - Issue 本文に必須フィールドが含まれることを確認
  - `GHE_TOKEN` 未設定時に適切なエラーを返すことを確認
  - 複数 PIR がある場合に複数 Issue が作成されることを確認

---

### P4-3: SAGE Analysis API 連携 ✅

**目的:** SAGE Analysis API から脅威アクター観測データを取得し、Likelihood スコアを実績ベースで補正する。Spanner には直接接続せず、`SAGE_API_URL` 経由でアクセス。

**追加依存:** `httpx`（P4-1 で追加済みであれば不要）

**環境変数（`config.py` に追加）:**
| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `SAGE_API_URL` | — | SAGE Analysis API の URL（例: `http://localhost:8000`）|

**作成ファイル:**
- `src/beacon/sage/client.py` — SAGE API クライアント
- `src/beacon/sage/__init__.py`

**`src/beacon/sage/client.py` 仕様:**
```python
class SageAPIClient:
    def __init__(self, base_url: str): ...

    def get_actor_observation_count(self, threat_actor_tags: list[str]) -> int:
        """
        SAGE の /asset-exposure を呼び出し、PIR タグに合致する
        ThreatActor が Spanner に存在する数を返す。
        SAGE API が応答しない場合は 0 を返してフォールバック。
        """
```
- 使用エンドポイント: `GET /asset-exposure`（SAGE 既存 API）
- タグ合致判定: レスポンス内の actor.tags と threat_actor_tags の積集合が空でなければカウント
- タイムアウト: 5秒。接続失敗は `WARNING` ログを出して 0 を返す（SAGE 未稼働時もパイプラインを止めない）

**`analysis/risk_scorer.py` の変更:**
```python
def score(
    elements, threat, *,
    use_llm=False, config=None,
    use_sage=False, sage_client=None,  # ← 追加
) -> RiskScore:
```
- `use_sage=True` かつ `sage_client` が提供された場合のみ観測カウントを取得
- `observation_count >= 1` → likelihood に +1（上限 5 を超えない）
- rationale に `SAGE観測: N件` を追記

**`cmd/generate_pir.py` の変更:**
- `--use-sage` フラグを追加（`SAGE_API_URL` が設定済みの場合のみ有効）

**テスト:**
- `tests/test_sage_client.py`
  - `httpx` を `unittest.mock` でモック
  - 観測アクターあり → likelihood +1 を確認
  - SAGE API タイムアウト → likelihood 変化なし・WARNING ログを確認
  - `use_sage=False`（デフォルト）では API 呼び出しが発生しないことを確認

---

### P4-4: Web UI (FastAPI + Jinja2) ✅

**目的:** PIR 生成・レビュー・編集・GHE 投稿を一画面で行える社内向け Web インターフェース。利用者増加時は Jinja2 → React SPA への移行を想定し、API ルートをフロントエンドと分離して設計する。

**追加依存:** `fastapi`, `uvicorn[standard]`, `python-multipart`, `jinja2`（`pyproject.toml` に追加）

**作成ファイル:**
```
src/beacon/web/
├── __init__.py
├── app.py              # FastAPI アプリ定義・ルート登録
├── session.py          # パイプライン結果を一時ファイルで管理
├── templates/
│   ├── base.html       # 共通レイアウト（ナビゲーション・CSS）
│   ├── index.html      # business_context.json アップロード画面
│   └── review.html     # PIR レビュー・編集・承認画面
cmd/web_app.py           # uvicorn 起動エントリポイント
```

**ルート定義 (`src/beacon/web/app.py`):**
| メソッド | パス | 処理 |
|---------|------|------|
| `GET` | `/` | index.html: ファイルアップロードフォーム |
| `POST` | `/generate` | パイプライン実行 → セッション保存 → `/review` にリダイレクト |
| `GET` | `/review` | review.html: PIR 一覧・編集フォーム・collection_plan 表示 |
| `POST` | `/review/save` | PIR フィールド（description/rationale/collection_focus）を編集保存 |
| `POST` | `/review/approve` | GHE Issue 作成（P4-2 の `github.py` を呼び出す）|
| `GET` | `/review/export` | `pir_output.json` をダウンロード |

**`cmd/web_app.py` 仕様:**
```
uv run python cmd/web_app.py [--host 127.0.0.1] [--port 8080] [--reload]
```

**セッション設計 (`session.py`):**
- パイプライン結果（PIR リスト・collection_plan・elements）を `$TMPDIR/beacon_session_{uuid}.json` に保存
- セッション ID を Cookie で管理（`itsdangerous` は使わず、ファイル名で管理）
- セッション TTL: 24時間（古いファイルは起動時にクリーンアップ）

**React SPA 移行時の互換性確保:**
- `GET /api/pir` → PIR JSON を返す REST エンドポイントを `app.py` に併設
- `POST /api/generate` → JSON レスポンスを返す REST エンドポイントを併設
- 将来 React に移行する際はこれらの API エンドポイントをそのまま使用し、Jinja2 テンプレートのみ差し替え

**テスト:**
- `tests/test_web_app.py`
  - `fastapi.testclient.TestClient` を使用
  - `POST /generate` でパイプラインをモックし、`/review` へのリダイレクトを確認
  - `GET /review` でセッションから PIR が表示されることを確認
  - `POST /review/save` でフィールド更新が永続化されることを確認
  - `GET /review/export` で有効な JSON が返ることを確認

---

## 優先度: Low（将来検討）

| 項目 | 内容 |
|------|------|
| Web UI → React 移行 | P4-4 の FastAPI + Jinja2 を React SPA に移行（利用者増加時）。`/api/*` エンドポイントは P4-4 で既に実装済みのため、フロントエンドのみ差し替え |
