# BEACON Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/). Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.8.0] — 2026-04-19

### Changed — Phase 7: MITRE+MISP-Only Threat Taxonomy (Breaking)

**Taxonomy is now fully auto-generated.** Hand-curated content removed; every
field in `schema/threat_taxonomy.json` is rebuilt from two upstream feeds:
MITRE ATT&CK Enterprise (STIX 2.1) and MISP Galaxy `threat-actor` cluster.

**Breaking schema changes** (`schema/threat_taxonomy.json`)
- Removed top-level fields: `industry_threat_map`, `business_trigger_map`,
  `supply_chain_threat_map`
- Removed per-category fields: `subgroups`, `additional_tags`
- Removed metadata field: `_metadata.last_manual_review`
- `actor_categories` restructured: `state_sponsored.<Country>` buckets
  (canonical names from MISP `cfr-suspected-state-sponsor` with alias
  normalization, e.g. `USA` → `United States`) + non-state buckets derived
  from MISP `cfr-type-of-incident`: `espionage`, `financial_crime`,
  `sabotage`, `subversion`
- `target_industries` now uses MISP coarse vocabulary only: `Private sector`,
  `Government`, `Military`, `Civil society` (previously 14 fine-grained
  industries)

**Breaking API changes**
- `beacon.analysis.threat_mapper.map_threats(elements, taxonomy)` —
  dropped `use_llm` and `config` parameters; LLM fallback path removed
- New module constant `_BEACON_TO_MISP_INDUSTRY` maps BEACON's 10 industry
  literals onto the 4 MISP coarse categories (defense→Military,
  government→Government, education→Civil society, else→Private sector)
- PIR tag vocabulary coarsened: emitted tags are now MISP-derived only
  (`apt-<country-slug>`, `espionage`, `financial-crime`, `sabotage`,
  `subversion`, `cybercriminal`). Removed: `ot-targeting`, `ip-theft`,
  `ransomware`, `cloud-targeting`, `supply-chain-attack`, `erp-targeting`,
  `targets-<country>`, `bec`, `fraud`, `double-extortion`, etc.

**Updater rewrite** (`cmd/update_taxonomy.py`)
- Rebuilds the entire JSON on every run; no incremental merge with prior
  hand-curated state
- New flags: `--mitre-url` / `--misp-url` (override upstream URLs),
  `--mitre-cache` / `--misp-cache` (read from local file, useful for
  air-gapped / test runs; canonical URLs are still written to
  `_metadata.sources`)
- STIX relationship-driven TTP extraction: iterates `relationship` objects
  with `type=uses` from `intrusion-set` → `attack-pattern`, not the
  deprecated `intrusion-set.x_mitre_techniques` field

**Removed**
- `src/beacon/llm/prompts/threat_tag_completion.md` — LLM fallback for
  dictionary misses. Deleted entirely; MISP coverage is broad enough that
  dictionary-miss cases are rare, and LLM-suggested tags cannot be traced
  to a source citation

**Trigger escalation relocation**
- `{m_and_a, ot_connectivity, ipo_or_listing}` escalation set is no longer
  driven by `business_trigger_map` (deleted). It now lives exclusively as
  a hardcoded constant in `src/beacon/analysis/risk_scorer.py:_recommend_level`,
  as a BEACON-internal operational rule separate from the MITRE/MISP feeds

**PIR clusterer** (`src/beacon/analysis/pir_clusterer.py`)
- `_FAMILY_TAGS`, `_FAMILY_ASSET_TAGS`, `_FAMILY_LABELS`,
  `_FAMILY_GROUP_KEYWORDS` rewritten to the new tag vocabulary
- Removed families: `ransomware`, `supply_chain`, `cloud`, `ot_ics`,
  `hacktivism`. Remaining: `state_sponsored`, `espionage`,
  `financial_crime`, `sabotage`, `subversion`, `cybercriminal`

**Tests**
- `tests/test_threat_mapper.py` — rewritten with synthetic MITRE+MISP-shaped
  fixture; added `TestDefenseIndustryMapping` (verifies every BEACON
  industry literal has a `_BEACON_TO_MISP_INDUSTRY` entry via
  `Organization.model_fields["industry"].annotation.__args__`)
- `tests/test_update_taxonomy.py` — rewritten around new builders
  (`_extract_group_ttps`, `_build_actor_categories`,
  `_build_geography_threat_map`); `TestMainCLI` covers `--mitre-cache` /
  `--misp-cache` behavior
- `tests/fixtures/sample_stix_bundle.json` — added `relationship` objects
  (5 entries) exercising `uses` + non-`uses` type filtering
- `tests/test_pir_clusterer.py` — expected family set updated to the new
  six families

**Documentation**
- `high-level-design.md` §4.2 — rewritten taxonomy description; deleted
  fields list; new matching logic (coarse industry + geography)
- `high-level-design.md` §5.3 — replaced `business_trigger_map` rationale
  pointer with a reference to the hardcoded trigger set in `risk_scorer.py`
- `high-level-design.md` §5.2 — example PIR JSON updated to MISP-derived
  tags
- `high-level-design.md` §8 directory tree — removed
  `threat_tag_completion.md` entry
- `docs/data-model.md` / `.ja.md` — "Threat Taxonomy Coverage" section
  rewritten: MITRE+MISP-only sources, new category axes, industry mapping
  table, geography matching rules
- `docs/setup.md` / `.ja.md` — "Updating the Threat Taxonomy" section
  rewritten: hand-edits to the JSON are now overwritten on the next run;
  document `--mitre-cache` / `--misp-cache` flags
- `docs/structure.md` / `.ja.md` — removed `threat_tag_completion.md`
  directory-tree entry

---

## [0.7.0] — 2026-04-11

### Added — Phase 6: SAGE Assets Generation and CTI Report STIX Extraction

**SAGE Assets Generation (`cmd/generate_assets.py`)**
- `src/beacon/analysis/assets_generator.py` — `generate_assets_json(ctx)` converts `BusinessContext.critical_assets` to SAGE-compatible `assets.json`; `_derive_asset_tags()` applies three-pass logic (network_zone_tag_map, data_type_tag_map, keyword matching) identical to `asset_mapper.py`; stable network segment IDs derived from `network_zone`; criticality mapped `critical→10.0 / high→8.0 / medium→5.0 / low→3.0`; `CriticalAsset.dependencies` converted to `asset_connections[]`
- `cmd/generate_assets.py` — CLI: `--context` (required), `--output` (default: `output/assets.json`), `--no-llm`; prints next-step instructions

**CTI Report STIX Extraction (`cmd/stix_from_report.py`)**
- `src/beacon/ingest/report_reader.py` — `read_report(source, max_chars=10_000)` auto-detects source type: PDF/URL via `markitdown` (converts to clean Markdown, strips nav/footer/ads); plain text/Markdown files read directly; all output truncated to `max_chars`; `_markitdown_convert()` lazily imports `MarkItDown` for testability
- `src/beacon/ingest/stix_extractor.py` — `extract_stix_objects()` calls Gemini via `call_llm_json("medium", ...)` with stix_extraction prompt; validates and filters to 8 known STIX types; handles bare array or wrapped `{"objects": [...]}` response; `build_stix_bundle()` wraps objects in STIX 2.1 bundle with unique `bundle--<uuid4>` ID; accepts `task` parameter override
- `src/beacon/llm/prompts/stix_extraction.md` — extraction prompt with full STIX 2.1 schemas for 7 object types and relationship guidance
- `cmd/stix_from_report.py` — CLI: `--input` (PDF path or URL, required; wrap URLs containing `?` in single quotes), `--output` (default: `output/stix_bundle.json`), `--task` (simple/medium/complex, default: medium), `--max-chars` (default: 10000); prints SAGE ETL follow-up command

**Dependency**
- `pyproject.toml` — added `markitdown[pdf]>=0.1.0`; converts PDFs and web articles to clean Markdown via pdfminer.six; 3–5× fewer characters than plain-text extraction, enabling 10,000-char default

**Tests**
- `tests/test_report_reader.py` — 13 tests: URL/HTTP conversion, PDF conversion, text/Markdown files, missing files, truncation (default + custom), markitdown import error
- `tests/test_stix_extractor.py` — 13 tests: ExtractStixObjects (9), BuildStixBundle (4)
- `tests/test_assets_generator.py` — 28 tests: NormalizeAssetId (3), CriticalityMap (4), InternetExposedZones (4), GenerateAssetsJson (17)
- 249 tests total (247 passed, 2 skipped) / lint clean

**Documentation**
- `docs/setup.md`, `docs/ja/setup.md` — new sections: "Generating SAGE assets.json" and "Extracting STIX bundles from CTI reports"; URL quoting note for zsh/bash; `--task` and `--max-chars` options documented
- `docs/dependencies.md` — `markitdown[pdf]` entry with rationale
- `high-level-design.md` — updated Section 3 to include new modules and commands
- `README.md`, `README.ja.md` — Overview updated to show all three output pipelines

---

## [0.6.0] — 2026-04-11

### Added — Phase 5: CriticalAsset Model, Input/Output Structure, Taxonomy Enrichment

**CriticalAsset Schema Extension**
- `src/beacon/ingest/schema.py` — new `CriticalAsset` Pydantic v2 model with 12 fields: `type`, `hostname`, `os_platform`, `network_zone`, `criticality`, `data_types`, `managing_vendor`, `supply_chain_role`, `dependencies`, `exposure_risk`; added `critical_assets: list[CriticalAsset]` to `BusinessContext`
- `src/beacon/analysis/element_extractor.py` — new `CriticalAssetDetail` dataclass; `ExtractedElements` extended with `org_regulatory_context`, `critical_asset_ids`, `critical_asset_details`; `has_ot_connectivity` now also checks `network_zone == "ot"` in `critical_assets`; `managing_vendor` added to `active_vendors`
- `src/beacon/analysis/asset_mapper.py` — `map_asset_tags()` processes `critical_asset_details`: keyword matching on function+name, `data_types` mapping, OT/DMZ zone → tag

**Bug Fix: regulatory_context**
- `src/beacon/generator/pir_builder.py` — fixed `getattr(elements, "regulatory_context", [])` that always returned `[]` (field never existed on `ExtractedElements`); corrected to `elements.org_regulatory_context`; added `{{CRITICAL_ASSETS}}` placeholder and `critical_assets_text` rendering

**Input/Output Directory Structure**
- `.gitignore` — added `input/` and `output/` (sensitive runtime data; not committed); `cmd/generate_pir.py` auto-creates output dir at runtime
- `cmd/generate_pir.py` — new defaults: `--context input/context.md`, `--output output/pir_output.json`, `--collection-plan output/collection_plan.md`; added `--save-context` option to persist intermediate `business_context.json` to `output/`

**Prompt Updates**
- `src/beacon/llm/prompts/context_structuring.md` — complete rewrite: added `critical_assets[]` to output schema, Section Recognition Guide, Crown Jewels vs Critical Assets distinction, supply chain mapping rules, language preservation rules
- `src/beacon/llm/prompts/pir_generation.md` — added `### Critical Assets` section with `{{CRITICAL_ASSETS}}` placeholder; instructions updated to reference supply chain assets in rationale and collection_focus
- `src/beacon/llm/prompts/threat_tag_completion.md` — complete rewrite: whitelist expanded to 40+ named groups across 7 categories; source citations added (MITRE ATT&CK, MISP Galaxy, BushidoUK Ransomware Tool Matrix); new tags: `apt-india`, `bec`, `fraud`, `double-extortion`, `targets-taiwan`, `targets-uk`, `targets-germany`, `targets-australia`

**Threat Taxonomy Enrichment (`schema/threat_taxonomy.json`)**
- Added `_metadata` with 6 source citations
- New actor categories: `cybercriminal` (FIN7, Scattered Spider, TA505), `insider_threat`, `state_sponsored.India` (SideWinder, Patchwork)
- China expanded: Salt Typhoon, Volt Typhoon, APT40, APT27 subgroups
- Russia expanded: Turla, TEMP.Veles subgroups
- DPRK expanded: BlueNoroff, TraderTraitor, Andariel subgroups
- 8 new ransomware groups: Akira, Play, Dark Angels, Hunters International, Medusa, BlackSuit, BianLian, Scattered Spider
- New industries: pharmaceutical, telecom, retail, automotive, aerospace
- New geographies: Germany, UK, Australia, Taiwan, Canada, India
- New triggers: regulatory_change, digital_transformation
- New section: `supply_chain_threat_map` (6 entries)
- All rationale fields translated to English (Rule 11)

**Asset Tag Enrichment (`schema/asset_tags.json`)**
- 10 new asset types: `email_gateway`, `vpn_remote_access`, `firewall_ngfw`, `siem`, `pki`, `database`, `devops_cicd`, `domain_controller` (multiplier 2.5), `file_server`, `api_gateway`
- New `network_zone_tag_map` section

**Documentation**
- `docs/context_template.md` — new English primary template for `input/context.md` (Rule 11 compliance)
- `docs/ja/context_template.md` — Japanese translation of context template
- `high-level-design.md` — updated sections 3, 4.1, 4.2, 9, 10

**Tests**
- `tests/test_element_extractor.py` — 10 new tests: `TestCriticalAssets` (7) and `TestCriticalAssetTagMapping` (3)
- `tests/fixtures/sample_context_manufacturing.json` — added `critical_assets` array (CA-001: SAP ERP / corporate, CA-002: EDI gateway / OT zone)
- `tests/test_report_builder.py`, `tests/test_sage_client.py` — updated `ExtractedElements` instantiation for new fields
- 183 tests total (181 passed, 2 skipped) / lint clean

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

- `tests/test_sage_compatibility.py` — Replaced SAGE-dependent `TestSAGEPIRFilterIntegration` with standalone `TestSAGEContractValidation`; validates field contracts without requiring the SAGE package (7 tests)
- Removed `tests/conftest.py` (no longer needed — SAGE src `sys.path` addition removed)
- `BEACON/README.md` — Updated test list table, added `SAGE required?` column, refreshed Project Structure
- `SAGE/README.md` — Added link to BEACON in PIR-Based Asset Weighting section
- `BEACON/high-level-design.md` — Removed `conftest.py` from directory tree
- 119 tests all pass / lint clean

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
- 117 tests total, all pass / lint clean (2 integration tests deselected)

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
