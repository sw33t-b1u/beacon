# BEACON API 安定性ポリシー

**ステータス**: Initiative H — 1.0 安定化のドラフト（サインオフ保留中）。
BEACON 1.0.0 から有効。

本ドキュメントは BEACON のコミット済み公開サーフェスと、それに適用される
後方互換性（BC）保証を列挙する。**Committed（コミット済み）** として列挙されていないものは
**Evolving（発展中）** であり、事前通知なしに任意のマイナーリリースで変更される可能性がある。

---

## 1. バージョニングポリシー（SemVer 2.0.0 厳格準拠）

BEACON は 1.0.0 以降、[Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)
を厳格に遵守する。

- **メジャー** (`X.0.0`) — §3 に列挙された Committed サーフェス項目に対する破壊的変更。
- **マイナー** (`1.X.0`) — 追加的変更（新規任意フィールド、新規エンドポイント、新規 CLI サブコマンド、新規環境変数）。Committed サーフェス項目を破壊してはならない。
- **パッチ** (`1.0.X`) — バグ修正のみ。サーフェス変更なし。

### 90 日間 BC 保証

Committed サーフェス項目は、導入されたリリースから **少なくとも 90 日間** BC が保証される。90 日後、破壊的変更は新しいメジャー（例: `2.0.0`）としてリリースされる場合がある。90 日間のウィンドウ内に発見された破壊的変更は、たとえ発見済みであっても次のメジャーまで延期される。

### 廃止パス

Committed サーフェス項目を削除するには:

1. **1.X.Y の CHANGELOG に告知**: 項目を `### Deprecated` としてマークし、削除予定バージョンを明記する。
2. **実行時に `DeprecationWarning` を出力**: 非推奨項目が使用された際に警告を発する。
3. **少なくとも 90 日間**、かつ廃止告知後の少なくとも 1 つのマイナーリリースを待つ。
4. **`2.0.0`**（またはそれ以降のメジャー）で削除する。

古いものを置き換える追加的な代替品（新しいフィールド/エンドポイント）は、ステップ 1 においてマイナーとしてリリースする。

---

## 2. クイックリファレンス

| サーフェス | Committed? | 初版 | 備考 |
|---|---|---|---|
| `pir_output.json` スキーマ | ✓ | 1.0.0 | `schema_version` フィールドに `"1.0.0"` が入る |
| `sources_candidate.yaml` | ✓ | 1.0.0 | TRACE `schema/sources.schema.json` に対してスキーマ検証される |
| `collection_plan.md` 構造 | ✓ | 1.0.0 | PIR ごとのセクション + 監視項目 + ソースリスト |
| `content_ja.json` スキーマ | ✓ | 1.0.0 | トップレベルセクションは固定; エントリのサブフィールドは追加的 |
| `content_ja.schema.json` | ✓ | 1.0.0 | content_ja.json の JSON Schema（draft 2020-12）|
| `source_aliases.json` | ✓ | 1.0.0 | 発行元の正規化マップ |
| `business_context.schema.json` | ✓ | 1.0.0 | オペレーター向けビジネスコンテキスト入力スキーマ |
| `source_attack_groups.derived.json` | ✗ | n/a | 自動導出; `scripts/derive_source_groups.py` で再生成 |
| `beacon` CLI エントリ + サブコマンド | ✓ | 1.0.0 | サブコマンド名 + 主要フラグは固定 |
| レガシー `python -m cmd.<name>` | （非推奨）| n/a | 1.0.0 で非推奨 → 2.0.0 で削除 |
| BEACON Web UI ルートパス + マルチアーティファクトビュー | ✓ | 1.0.0 | HTML/CSS の内部実装は Evolving のまま |
| 環境変数（§5）| ✓ | 1.0.0 | 名前 + 意味 + デフォルト値を固定 |
| その他の環境変数（LLM モデル選択、GHE_* など）| （内部）| n/a | デプロイメント固有; 変更される可能性あり |
| `schema/asset_tags.json` / `surface_ttp_map.json` / `threat_taxonomy.json` / `trigger_keywords.json` | （オペレーターがカスタマイズする内部データ）| n/a | BEACON は BC を保証しない; オペレーターがカスタマイズ可能 |
| 内部 Python モジュール（`src/beacon/*` 非公開シンボル）| ✗ | n/a | アンダースコア付きおよびドキュメント未記載のヘルパーは変更される可能性あり |

---

## 3. Committed サーフェス — 詳細

### 3.1 PIR 出力スキーマ（`pir_output.json`）

Pydantic モデルは `src/beacon/generator/pir_builder.PIROutputDocument` およびその依存モデル。JSON Schema は `cmd/generate_schemas.py`（現在は §4 の `beacon schema-regenerate`）によって `schema/pir_output.schema.json` に再生成される。

**Committed トップレベル**:
- `schema_version: "1.0.0"` — 必須文字列フィールド; コンシューマーがこの値でゲートを設ける。TRACE 1.12.0 は `{"1.0.0"}` のみを受け付ける。
- `pirs: list[PIROutput]` — 必須、順序付き。

**Committed `PIROutput` フィールド**（一部 — 完全なリストはスキーマを参照）:
- `pir_id`、`decision_point`、`priority`、`intelligence_level`、`collection_focus[]`、`valid_from`、`valid_until`
- `prioritized_actors[]`（Initiative D + E より）
- `mitre_attack_groups: list[str]`（Initiative F フェーズ 2）
- `score_breakdown: ScoreBreakdown` （以下を含む）:
  - `intent: IntentComponent`（score、motivation_alignment、industry_match、`ir_observed`）
  - `capability: CapabilityComponent`（score、sophistication_score、ttp_count_norm、recency_active_campaigns、tool_usage、targeting_persistence、evasion_capability、depth、breadth）
  - `opportunity: OpportunityComponent`（score、victimology_match、geographic_match、surface_ttp_coverage）
  - `data_quality: DataQualityComponent`（degraded、missing_sources、`ir_boost_skipped` — G フェーズ 6）
- `rationale: Rationale`（text、intent_factors、capability_factors、opportunity_factors）

**追加的（非破壊的）**:
- 既存モデルへの新規任意フィールドの追加。
- 新規 `score_breakdown` サブコンポーネントの追加（オペレーターによる追加も可）。

**破壊的（2.0.0 が必要）**:
- 必須フィールドの削除または改名。
- `schema_version` を `"1.X.Y"` 以外の値に変更。

### 3.2 `sources_candidate.yaml`

`beacon pir-generate`（旧 `cmd/generate_pir.py --sources-candidate`）で生成される。
各エントリは TRACE `schema/sources.schema.json` の形式に従う（url、label、task、max_chars、pir_ids、feed_type）。URL フィールドはオペレーターが記入するプレースホルダー `<TODO: fill from candidate>`。

**Committed**: ファイル先頭のヘッダー構造（タイムスタンプ、`schema_version: "1.0.0"`、Capability ウィンドウベースラインの注記 — 「BEACON 1.0.0 default-window (90-day) baseline」）、エントリごとのヘッダーコメントの形式（tier / region / industry / evidence_attack_groups）、`pir_ids[]` の関連付け。

### 3.3 `collection_plan.md`

P1-P4 エントリをカバーする Markdown 出力: PIR ごとのセクションに優先度バッジ、インテリジェンスレベル、collection_focus のバレットポイント、`source_matcher` からの推奨ソースが含まれる。加えて監視項目（P3/P4）とトリガーベースの収集アクション。

**Committed**: セクションの順序（PIR セクションが監視項目より前）、優先度バッジの形式（`[P1]` / `[P2]` / `[P3]` / `[P4]`）、「Recommended Sources」サブセクションの存在。

### 3.4 `content_ja.json` + `content_ja.schema.json`

Initiative F フェーズ 1.7 で導入された多次元ソース/IR スキーマ。

**Committed トップレベルセクション**（改名または削除不可）:
- `intelligence_requirements: list` — CU-GIR Framework の 10 進数 ID + 5W1H EEI + mitre_attack_groups
- `sources: list` — tier / region / industry_focus / evidence_attack_groups / tlp / requires_membership / evidence_derivation
- `trigger_actions: dict` — キーワード → アクション記述子
- `level_frequency: dict` — intelligence_level → 頻度ラベル
- `table: dict` — 収集計画テーブルのラベル（cti_team、ot_team など）

**追加的（非破壊的）**:
- 任意のリストセクションへの新規エントリの追加（オペレーターによる追加も可）。
- エントリへの新規任意サブフィールドの追加（例: `intelligence_requirements[]` に `valid_window_days` を追加）。

**破壊的（2.0.0 が必要）**:
- トップレベルセクションの改名。
- エントリから必須サブフィールドを削除。
- `gir_id` からの CU-GIR 10 進数 ID 規約の削除。

### 3.5 `source_aliases.json`

ATT&CK `intrusion-set.external_references[].source_name` のバリアントに一致する
プレフィックスパターンへの正規発行元名の手動管理マップ。
オペレーターは追加の発行元で拡張可能。

**Committed**: ファイル形式（dict[canonical_name, list[prefix_str]]）、場所（`schema/source_aliases.json`）。

### 3.6 `business_context.schema.json`

PIR 生成を駆動するオペレーター提供のビジネスコンテキストの JSON Schema。
`beacon assets-generate` と `beacon pir-generate` で使用される。

**Committed**: トップレベルの必須フィールド（organization、industry、geographies、business_critical_assets など）— 完全なリストはファイルを参照。

### 3.7 `beacon` CLI エントリ + サブコマンド（フェーズ 6 成果物）

Initiative H フェーズ 6 は `beacon` を click `Group` エントリポイントとして導入する。
サブコマンドは既存の `cmd/*.py` ロジックをラップする。1.0.0 からの
オペレーター向け公開サーフェス:

| サブコマンド | 置き換え対象 | 目的 |
|---|---|---|
| `beacon pir-generate` | `cmd/generate_pir.py` | PIR + 収集計画 + ソース候補を生成; 成功時に Web UI を自動起動 |
| `beacon assets-generate` | `cmd/generate_assets.py` | アセットバンドルを生成 |
| `beacon identity-generate` | `cmd/generate_identity_assets.py` | ID（人物/組織）アセットバンドルを生成 |
| `beacon accounts-generate` | `cmd/generate_user_accounts.py` | ユーザーアカウントバンドルを生成 |
| `beacon submit-review` | `cmd/submit_for_review.py` | 出力をレビューシステムに提出 |
| `beacon taxonomy-refresh` | `cmd/update_taxonomy.py` | MITRE ATT&CK + MISP Galaxy から脅威タクソノミーを同期 |
| `beacon misp-cache-refresh` | `cmd/refresh_misp_cache.py` | MISP タクソノミーキャッシュを更新 |
| `beacon web` | `cmd/web_app.py` | PIR 生成をトリガーせずにレビュー UI を起動 |

**Committed**: サブコマンド名 + 各サブコマンドの主要フラグ（例: `pir-generate --output-dir`、`pir-generate --no-sage`、`pir-generate --sources-candidate`）。

**Evolving**: オプションフラグのデフォルト値（例: `--tlp-max` のデフォルト）、ヘルプテキストの文言、出力フォーマット。

**非推奨（2.0.0 で削除）**: `python -m cmd.<name>` の呼び出し構文。cmd モジュールは後方互換のため 1.x には残るが、統一された `beacon` エントリへの移行を促す `DeprecationWarning` を出力する。

### 3.8 BEACON Web UI（`beacon web` + `beacon pir-generate` による自動起動）

`beacon pir-generate` が正常に完了すると、BEACON はバックグラウンドでローカル
Web サーバーを自動起動し、URL を出力する。

**Committed ルートパス**（HTML/CSS の内部実装は Evolving のまま）:
- `/` — 直近の `--output-dir` 内のすべての生成アーティファクトを一覧するランディングページ: `pir_output.json`、`assets.json`、`identity_assets.json`、`user_accounts.json`、`collection_plan.md`、`sources_candidate.yaml`。
- `/review/pir/{pir_id}` — `prioritized_actors[]` のビュー + 編集（exclude / manual_likelihood_override / rationale_append）。編集はセッション内のみ保持（SAGE への書き戻しなし）; 下流のオペレーターワークフロー向けに JSON エクスポート可能。
- `/review/artifacts/{filename}` — その他のアーティファクトファイルの読み取り専用ビューアー。

**Evolving**: HTML 構造、CSS、JavaScript、UI を提供する内部 API ルート。

### 3.9 環境変数（Committed）

| 環境変数 | デフォルト | 目的 |
|---|---|---|
| `ACTIVITY_WINDOW_DAYS` | `90` | Capability の `recency_active_campaigns` ウィンドウ。6 ヶ月トレンドモードの場合は `180` を設定 |
| `BEACON_IR_LOOKBACK_DAYS` | `365` | IR ブースト計算のための SAGE `GET /api/incidents` クエリウィンドウ |
| `SAGE_API_URL` | `""` | SAGE REST API の URL。空 = SAGE 呼び出しなし（`--no-sage` と同等）|
| `SAGE_API_AUTH_TOKEN` | `""` | SAGE API 用 Bearer トークン。設定済みの場合は送信; 未設定の場合はヘッダーなし |

**その他の環境変数**（デプロイメント固有、Committed 対象外）:
- LLM モデル選択: `BEACON_LLM_SIMPLE`、`BEACON_LLM_MEDIUM`、`BEACON_LLM_COMPLEX`、`BEACON_LLM_MAX_OUTPUT_*`
- GCP: `GCP_PROJECT_ID`、`VERTEX_LOCATION`
- GitHub Enterprise: `GHE_TOKEN`、`GHE_REPO`、`GHE_API_BASE`

これらはマイナーリリースで名前やデフォルト値が変更される可能性がある — オペレーターはデプロイメントごとに明示的に設定すること。

---

## 4. Evolving（BC 保護対象外）

以下はオペレーターの認識のために文書化されているが、BC 保証の対象外。
任意のマイナーリリースで変更される可能性がある。

- **内部 Python モジュール** — `src/beacon/` 配下の、文書化された API サーフェス経由で公開されていないもの。アンダースコア付きおよびドキュメント未記載のヘルパーは予告なしに変更される可能性がある。
- **`generate_schemas.py`**（または `beacon schema-regenerate` の形式）— Pydantic モデルから JSON Schema を再生成する開発ツール。オペレーターは直接呼び出さない。
- **HTML/CSS/JavaScript** — `src/beacon/web/templates/` および `src/beacon/web/static/` 内のもの。ルートパス（§3.8）は Committed だが、レンダリングされる HTML 構造は機能追加のために変更される可能性がある。
- **`schema/asset_tags.json`** — オペレーターがカスタマイズするタグタクソノミー。BEACON はマイナーリリースでデフォルトタグを追加する可能性がある。
- **`schema/surface_ttp_map.json`** — サーフェス → TTP マッピングデータ。外部ソースから更新される。
- **`schema/threat_taxonomy.json`** — `beacon taxonomy-refresh` 経由で MITRE ATT&CK + MISP Galaxy から自動生成される。
- **`schema/trigger_keywords.json`** — 年次脅威レポート取り込みとともに発展するトリガーキーワードデータ。

---

## 5. クロスリポジトリ依存関係

BEACON の Committed サーフェスは以下に依存する:

- **TRACE `schema/sources.schema.json`**（TRACE 1.12.0+）: `sources_candidate.yaml` の検証に使用。
- **SAGE `GET /api/incidents`**（SAGE 1.0.0+）: `beacon pir-generate` の IR ブースト計算に使用。
- **MITRE ATT&CK Enterprise STIX バンドル**（導出時に読み取り、BEACON リポジトリにはコミットしない）: `source_attack_groups.derived.json` の再生成に使用。
- **Intel 471 CU-GIR Framework**（GitHub STIX JSON）: IR `gir_id` タクソノミーキーに使用。

完全な引用インベントリ: `docs/citations.md`。

---

## 6. 2.0.0 トリガー例

どのような変更が 2.0.0 リリースを強制するかを文書化することで、
オペレーターが BC 保証について判断しやすくなる:

- `pir_output.json` から `schema_version` フィールドを削除。
- `content_ja.json` で `intelligence_requirements` を `requirements` に改名。
- Likelihood 計算式を `Intent × Capability × Opportunity` から非乗算形式に変更（数値が変わる）。
- `beacon pir-generate` サブコマンドまたはその `--output-dir` フラグを削除。
- `BEACON_IR_LOOKBACK_DAYS` 環境変数を削除。
- `/review/pir/{pir_id}` Web UI ルートを削除。

既存のデプロイメントの動作を変更しないデフォルト値が設定されている限り、
新規フィールド、新規エンドポイント、新規サブコマンド、新規環境変数の追加は
常にマイナーリリースで許可される。

---

## 7. メンテナンス

新しい Committed サーフェス項目が導入されるか、Committed 項目が非推奨化されるたびに
本ドキュメントを更新すること。各エントリには以下を記録する:

- 項目名 + 最初のコミット時のバージョン
- 廃止ステータス + 削除予定バージョン（該当する場合）
- コントラクトが記述されているソースファイル / スキーマへのクロスリファレンス

---

*Initiative H — 1.0 安定化。BEACON 1.0.0 から有効。*
