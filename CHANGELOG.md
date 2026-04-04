# BEACON Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/). Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.5.0] — 2026-04-04

### Added — Phase 4: MITRE Auto-Update, GHE Review, SAGE API, Web UI

**P4-1: MITRE ATT&CK Taxonomy Auto-Update**
- `cmd/update_taxonomy.py` — fetches the latest MITRE CTI STIX bundle from GitHub and updates `schema/threat_taxonomy.json`; preserves manually managed fields (`geography_threat_map`, `industry_threat_map`, `business_trigger_map`); `--dry-run` mode prints diff without writing
- `tests/fixtures/sample_stix_bundle.json` — STIX fixture for unit tests
- `tests/test_update_taxonomy.py` (16 tests)

**P4-2: PIR Review Workflow (GHE Issues)**
- `src/beacon/review/github.py` — `GHEClient` creates/comments on GitHub/GHE Issues; `build_issue_body()` renders Markdown with review checklist; `submit_pirs_for_review()` orchestrates multi-PIR submission
- `cmd/submit_for_review.py` — CLI: `--pir pir_output.json [--collection-plan collection_plan.md]`
- `src/beacon/config.py` — added `GHE_TOKEN`, `GHE_REPO`, `GHE_API_BASE` config fields
- `tests/test_github_review.py` (13 tests)

**P4-3: SAGE Analysis API Integration**
- `src/beacon/sage/client.py` — `SageAPIClient.get_actor_observation_count()` queries `GET /asset-exposure`; 5 s timeout; returns 0 on any failure (fail-open design)
- `src/beacon/analysis/risk_scorer.py` — added `use_sage` / `sage_client` parameters; observation count ≥ 1 boosts likelihood by +1 (capped at 5); `SAGE観測: N件` appended to rationale
- `cmd/generate_pir.py` — added `--use-sage` flag; requires `SAGE_API_URL` to be set
- `src/beacon/config.py` — added `SAGE_API_URL` config field
- `tests/test_sage_client.py` (12 tests)

**P4-4: Web UI (FastAPI + Jinja2)**
- `src/beacon/web/app.py` — routes: `GET /`, `POST /generate`, `GET /review`, `POST /review/save`, `POST /review/approve`, `GET /review/export`; REST API mirrors: `GET /api/pir`, `POST /api/generate`
- `src/beacon/web/session.py` — session management via `$TMPDIR/beacon_session_{uuid}.json`; 24 h TTL
- `src/beacon/web/templates/` — `base.html`, `index.html`, `review.html` (Jinja2)
- `cmd/web_app.py` — uvicorn launcher: `--host`, `--port`, `--reload`
- `tests/test_web_app.py` (12 tests)
- 183 tests total, all pass / lint clean

**Dependencies added (`pyproject.toml`)**
- Runtime: `httpx>=0.27.0`, `fastapi>=0.111.0`, `uvicorn[standard]>=0.30.0`, `python-multipart>=0.0.9`, `jinja2>=3.1.0`
- All additions documented in `docs/dependencies.md`

**Rule compliance fixes**
- `docs/dependencies.md` updated for all Phase 4 additions (Rule 18)
- `.env.example` created with all supported environment variables (Rule 24)
- `make check` now includes `audit` (`vet lint test audit`) — Rule 21
- English-only source comments enforced (Rule 11)

---

## [0.4.0] — 2026-04-04

### Changed — Separate repository preparation (Option B)

- `tests/test_sage_compatibility.py` — `TestSAGEPIRFilterIntegration` を SAGE 非依存の `TestSAGEContractValidation` に置き換え。SAGE パッケージ不要でフィールド契約を検証（7テスト）
- `tests/conftest.py` を削除（SAGE src の sys.path 追加が不要に）
- `BEACON/README.md` — テスト一覧表・`SAGE required?` 列・Project Structure 更新
- `SAGE/README.md` — PIR-Based Asset Weighting セクションに BEACON へのリンクを追加
- `BEACON/high-level-design.md` — ディレクトリツリーから `conftest.py` を削除
- 119テスト all pass / lint clean

---

## [0.3.0] — 2026-04-04

### Added — Phase 3: Collection Plan & SAGE Compatibility

**Collection Plan Generator**
- `src/beacon/generator/report_builder.py` — `build_collection_plan()` generates `collection_plan.md` with P3/P4 watch items, trigger-specific collection actions, recommended sources per threat category, and collection frequency table
- `cmd/generate_pir.py` — `--collection-plan FILE` option added; invokes `build_collection_plan` + `write_collection_plan` after PIR generation

**SAGE Compatibility**
- `tests/test_sage_compatibility.py` (21 tests) — static schema validation without Spanner: field presence, field types, ISO date format, PIR JSON round-trip, and live `PIRFilter` integration tests (`is_relevant_actor`, `adjust_asset_criticality`, `build_targets`)
- `tests/conftest.py` — adds `SAGE/src` to `sys.path` for cross-package tests

**Tests**
- `tests/test_report_builder.py` (13 tests) — covers: PIR-covered labelling, below-threshold messaging, trigger inclusion/exclusion, `write_collection_plan` file output
- 合計 117テスト all pass / lint clean（統合テスト 2件 deselected）

**Documentation**
- `docs/sage_integration.md` — manual ETL verification procedure: generate → validate → deploy → run ETL → verify `pir_adjusted_criticality` via Spanner CLI

---

## [0.2.0] — 2026-04-04

### Added — Phase 2: Vertex AI LLM Integration

**LLM Client**
- `src/beacon/llm/client.py` — Vertex AI Gemini client with `call_llm` / `call_llm_json` / `load_prompt`; module-level try/except import for testability
- `src/beacon/llm/prompts/context_structuring.md` — one-shot MD→BusinessContext JSON prompt
- `src/beacon/llm/prompts/pir_generation.md` — PIR text augmentation prompt (description / rationale / collection_focus)
- `src/beacon/llm/prompts/threat_tag_completion.md` — dictionary fallback threat tag completion prompt

**LLM Integration in Pipeline**
- `ingest/context_parser.py` — `parse_markdown()` implemented (Vertex AI `gemini-2.5-flash-lite`, one-shot)
- `analysis/threat_mapper.py` — LLM fallback via `use_llm=True`; called only when dictionary yields zero matched categories
- `generator/pir_builder.py` — LLM text augmentation via `use_llm=True`; dictionary drafts passed as context to `gemini-2.5-flash`
- `analysis/risk_scorer.py` — LLM scoring assist via `use_llm=True` + `gemini-2.5-pro`; called only when no dictionary basis

**Tests**
- `tests/test_llm_client.py` (15 tests) — Vertex AI fully mocked; `@pytest.mark.integration` for real API smoke test
- `tests/test_context_parser_md.py` (8 tests) — Markdown path with mock; integration test for real LLM call
- `tests/fixtures/sample_context_finance.md` — finance sector context document in English

**Configuration**
- `pyproject.toml` — added `integration` pytest marker
- `Makefile` — added `test-integration` target (runs `@pytest.mark.integration` tests)

---

## [0.1.0] — 2026-04-04

### Added — Phase 1: Dictionary-Based Pipeline

**Project Foundation**
- `pyproject.toml` — project config (pydantic, google-cloud-aiplatform, structlog)
- `Makefile` — `check` / `generate` / `validate` / `test` / `audit` targets
- `src/beacon/config.py` — environment-variable based configuration (GCP_PROJECT_ID, VERTEX_LOCATION, BEACON_LLM_*)
- `docs/dependencies.md` — dependency rationale (Rule 18 compliance)

**Input Schema (Pydantic v2)**
- `src/beacon/ingest/schema.py` — `BusinessContext`, `Organization`, `StrategicObjective`, `Project`, `CrownJewel`, `SupplyChain`, `RecentIncident`
- `src/beacon/ingest/context_parser.py` — JSON parser + `parse_markdown()` stub (NotImplementedError)

**Dictionary Files**
- `schema/threat_taxonomy.json` — industry × geography × motivation → threat actor tags (MITRE ATT&CK Groups v15; Big 4 + ransomware + hacktivist)
- `schema/asset_tags.json` — asset type → SAGE tag mapping with criticality_multiplier

**Pipeline (Steps 1–5, dictionary-only)**
- `src/beacon/analysis/element_extractor.py` — Step 1: business element extraction + business trigger detection
- `src/beacon/analysis/asset_mapper.py` — Step 2: element → asset tags
- `src/beacon/analysis/threat_mapper.py` — Step 3: industry × geography × trigger → threat profile
- `src/beacon/analysis/risk_scorer.py` — Step 4: Likelihood × Impact scoring + intelligence level recommendation
- `src/beacon/generator/pir_builder.py` — Step 5: SAGE-compatible PIR JSON output (P1/P2 only, composite ≥ 12)

**CLI**
- `cmd/generate_pir.py` — `--context FILE --taxonomy FILE --output FILE --no-llm`
- `cmd/validate_pir.py` — PIR JSON SAGE compatibility validation
- `cmd/generate_schemas.py` — generate JSONSchema from Pydantic models

**Tests (56 tests, all pass)**
- `tests/test_element_extractor.py` — 15 tests
- `tests/test_threat_mapper.py` — 13 tests
- `tests/test_risk_scorer.py` — 12 tests
- `tests/test_pir_builder.py` — 16 tests
- `tests/fixtures/sample_context_manufacturing.json` — manufacturing × Japan × OT fixture
