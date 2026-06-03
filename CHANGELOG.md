# BEACON Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/). Versioning follows [Semantic Versioning](https://semver.org/).

---

## [2.1.2] — 2026-06-03

### Changed

- Promote `google-cloud-storage` from optional `[gcs]` extra to main
  `dependencies`. GCS is the de facto deploy target (Cloud Run +
  `BEACON_STORAGE=gcs`), and `uv run` implicit resync was dropping
  the extra and producing `ModuleNotFoundError: google.cloud` at
  container startup. Mirrors the TRACE 2.1.1 structural fix.
  The `[gcs]` extras section has been removed; existing
  `uv sync --extra gcs` invocations should drop the `--extra gcs`
  flag.

---

## [2.1.1] — 2026-06-03

### Fixed
- Web pipeline now writes `pir_output.json` with the canonical envelope
  (`{"schema_version": "2.0.0", "pirs": [...]}`) on all four emit paths:
  `/pir/generate` storage persist, `/pir/export`, `/review/export`, and
  `/api/generate`. The CLI (`cmd/generate_pir.py`) already emitted the
  envelope via `PIROutputDocument`; the web layer wrote a bare list,
  which SAGE 1.0.0+ `PIRFilter` and TRACE 2.0.0+ `PIRDocument` both
  reject. Added `wrap_envelope()` in `pir_builder` so the wrap helper
  shares the schema_version default with `PIROutputDocument`.


## [2.1.0] — 2026-05-28

### Added

- PIR generation (CLI + web) now also emits `assets.json`, `identity_assets.json`,
  and `user_accounts.json` drafts from the same context in a single `beacon pir-generate`
  invocation (or web `/pir/generate` call). Stored under the `assets` StorageBackend
  category with filenames `assets_<YYYYMMDDHHmm>.json`,
  `identity_assets_<YYYYMMDDHHmm>.json`, and `user_accounts_<YYYYMMDDHHmm>.json`.
  `asset_vulnerabilities` and `actor_targets` remain empty drafts (filled after STIX ETL).
- Web Identity and Accounts tabs for completing identity_assets / user_accounts draft fields.
- `beacon schema-regenerate` subcommand — regenerates JSON Schema files from Pydantic
  models into `schema/` (replaces `python -m cmd.generate_schemas`).

### Removed

- Standalone `python -m cmd.<name>` / `python cmd/<name>.py` invocation form for all
  `cmd/` modules. The `__main__` entry blocks and `_from_beacon_cli` / `DeprecationWarning`
  machinery have been deleted. Use `beacon <subcommand>` exclusively (see §3.7 of
  `docs/api-stability.md`).

---

## [2.0.0] — 2026-05-28

**Breaking: CIO scoring field rename.** The actor-triage score_breakdown
contract in `pir_output.json` changed in a backward-incompatible way.
`schema_version` bumps to `"2.0.0"`; consumers must update.

### Changed (BREAKING)

- `score_breakdown.capability.tool_sophistication` renamed to
  `tool_usage`.
- `score_breakdown.capability.ir_observed_capability` and
  `score_breakdown.opportunity.ir_observed_opportunity` removed; replaced
  by a single binary `score_breakdown.intent.ir_observed` (1.0 = actor
  has attacked the org in the IR lookback window, 0.5 otherwise).
- Likelihood aggregation: Depth and Opportunity are now 3-factor
  geometric means (was 4-factor); `ir_observed` multiplies into Intent.
- `pir_output.json` `schema_version` field: `"1.0.0"` → `"2.0.0"`.

### Removed

- 90-day BC guarantee from `docs/api-stability.md` (policy simplified).

### Notes

- Paired with TRACE 2.0.0 (ScoreComponent validation updated to match).
- SAGE is unaffected (consumes score_breakdown opaquely via rationale_json).

---

## [1.1.0] — 2026-05-25

**Initiative I — Unified Dashboard + Storage Abstraction.** Paired
triple: BEACON 1.1.0 + SAGE 1.1.0 + TRACE 1.13.0.

### Added

- **StorageBackend abstraction layer** — `LocalStorage` (filesystem)
  and `GCSStorage` (Google Cloud Storage) implementations behind an
  ABC. Artifacts are written to category-based paths (`pir/`,
  `assets/`, `stix/`, `plans/`) with `YYYYMMDDHHmm` timestamps.
  Env vars: `BEACON_STORAGE`, `BEACON_STORAGE_BASE_DIR`,
  `BEACON_GCS_BUCKET`, `BEACON_GCS_PREFIX`.
- **5-tab unified web dashboard** — replaces the 2-tab Generate/Review
  layout with Dashboard / PIR / Collection / Threats / Settings tabs.
- **PIR tab** — merges Generate + Review into one page with
  StorageBackend auto-load of existing PIR files.
- **Collection tab** — runs TRACE `crawl-single` / `crawl-batch` via
  subprocess from the web UI. Shows crawl history from
  `crawl_state.json`.
- **Threats tab** — SAGE API proxy with actor name search, TTP
  display, and per-asset threat summary. Time-range presets
  (1M/3M/6M/1Y/custom).
- **Dashboard tab** — pipeline-wide summary: PIR count, collection
  status, choke-points top-5, recent incidents.
- **Settings tab** — persistent configuration via
  `.beacon_settings.json` (priority: env > file > default). SAGE
  connection test, storage mode switching.
- `beacon.trace.runner` module for TRACE subprocess integration.
- `beacon.settings.SettingsManager` for settings persistence.

### Deprecated

- `beacon submit-review` CLI — replaced by web approval flow.
  Scheduled for removal in BEACON 2.0.0.

---

## [1.0.0] — 2026-05-24

**Initiative H — 1.0 Stabilization release.** BEACON 1.0.0 commits
to the public surface documented in `docs/api-stability.md` under a
90-day backward-compatibility guarantee. Paired triple: BEACON 1.0.0
+ TRACE 1.12.0 + SAGE 1.0.0.

### Committed surface

See `docs/api-stability.md` §3 for the authoritative inventory. Summary:

- PIR output schema (`schema_version: "1.0.0"` from this release;
  TRACE 1.12.0+ accepts only `"1.0.0"`).
- `sources_candidate.yaml`, `collection_plan.md`, `content_ja.json`
  (multi-dimensional schema from Initiative F),
  `content_ja.schema.json`, `source_aliases.json`,
  `business_context.schema.json`.
- Unified `beacon` console-script entry + 8 subcommands.
- Web UI route paths + multi-artifact landing view.
- Environment variables: `ACTIVITY_WINDOW_DAYS`,
  `BEACON_IR_LOOKBACK_DAYS`, `SAGE_API_URL`, `SAGE_API_AUTH_TOKEN`.

### Migration guide (operator steps)

The Initiative H triple release is a coordinated cut over the three
repos. Apply in order:

1. **BEACON 1.0.0** (this release). Re-run `beacon pir-generate`
   (or the legacy `python -m cmd.generate_pir`) so the emitted
   `pir_output.json` carries `schema_version: "1.0.0"`. TRACE 1.12.0
   will reject any prior version with a per-version error message.
2. **TRACE 1.12.0**. Strict validator restricted to
   `schema_version: "1.0.0"`. Wrapped envelope required
   (`{"schema_version": "1.0.0", "pirs": [...]}`); bare-list inputs
   are rejected with the migration message.
3. **SAGE 1.0.0**. BEACON 0.12.x compatibility shims removed
   (`HIGH_VALUE_IMPERSONATION_ROLES`, related upsert branches);
   identity_assets must carry `is_high_value_impersonation_target`
   directly. PIR ingest requires the wrapped envelope.

Operators on BEACON ≤ 0.12.x must upgrade BEACON before SAGE
1.0.0 deployment.

### Forward-looking note

BEACON 1.0.0 starts a **90-day backward-compatibility window** for
every item listed in `docs/api-stability.md` §3 (Committed surface).
Within that window:

- **Minor releases** (`1.X.0`) ship additive changes only —
  new optional fields, new endpoints, new CLI subcommands, new env
  vars. Existing committed items keep working unchanged.
- **Breaking changes** to any committed surface item require a new
  major release (`2.0.0`). Deprecation path: announce in 1.X.Y
  CHANGELOG + emit `DeprecationWarning` at runtime + remove in
  `2.0.0` after the 90-day BC window and at least one further minor.

Items marked Evolving in `docs/api-stability.md` §4 (internal Python
modules, HTML/CSS internals, operator-curated data files, dev tools)
remain free to change in any minor.

### Added — Initiative H Phase 6: unified `beacon` CLI + web UI auto-launch

- New `beacon` console script (`beacon.cli:cli`) exposes the eight
  committed subcommands from `docs/api-stability.md` §3.7:
  `pir-generate`, `assets-generate`, `identity-generate`,
  `accounts-generate`, `submit-review`, `taxonomy-refresh`,
  `misp-cache-refresh`, `web`. Each subcommand delegates to the existing
  `cmd/*.py` `main(argv)` and forwards `_from_beacon_cli=True` to
  suppress the legacy deprecation banner.
- `beacon pir-generate` introduces a unified `--output-dir` flag that
  expands into `--output`, `--collection-plan`, and
  `--sources-candidate` under that directory. On success the review web
  UI auto-launches in a detached subprocess and prints its URL; the
  new `--no-web` flag opts out.
- `src/beacon/web/launcher.py` (NEW) spawns `cmd/web_app.py` on a free
  local port, forwards `BEACON_OUTPUT_DIR` to the child env, polls the
  server until ready, and returns the URL non-blocking.
- `src/beacon/web/app.py` extends the landing page (`GET /`) with a
  multi-artifact table — `pir_output.json`, `assets.json`,
  `identity_assets.json`, `user_accounts.json`, `collection_plan.md`,
  `sources_candidate.yaml` — scanned from `BEACON_OUTPUT_DIR` (default
  `./output`). New routes `GET /review/pir/{pir_id}` (PIR-scoped
  review) and `GET /review/artifacts/{filename}` (read-only viewer,
  plus `/raw` for download) match the surface committed in §3.8.
- `cmd/*.py` modules gain a module-level `.. deprecated:: 1.0.0` note
  + a runtime `DeprecationWarning` printed to stderr when invoked
  directly (suppressed when invoked through the `beacon` entry point).
  The legacy invocation form remains supported through BEACON 1.x for
  backward compatibility.
- Tests: 71 new (`tests/test_cli.py` 32, `tests/test_web_launcher.py`
  12, `tests/test_web_multi_artifact.py` 27); brings the suite from
  749 → 820 passing.
- `click >= 8.1.0` promoted from transitive to direct dependency
  (documented in `docs/dependencies.md`).

### Changed — RULES.md compliance pass

- `high-level-design.md` moved from the project root into `docs/` per
  Rule 27, matching the fix shipped in TRACE and SAGE. The file remains
  gitignored per maintainer policy; the `.gitignore` entry is updated
  to the new path. `docs/structure.md` / `docs/structure.ja.md` updated
  to reflect the relocation.

### Docs — citations retroactive paraphrase pass

- `docs(citations)`: retroactive paraphrase pass — proprietary vendor
  verbatim quotes in `schema/surface_ttp_map.json` (35 entries) and
  `docs/triggers.md` (CrowdStrike GTR 2025, Mandiant M-Trends 2026,
  IBM Cost of a Data Breach 2025, Cloudflare 2026 Threat Report,
  Dragos 2026 OT Report, APWG Q4 2025) rewritten to paraphrase + cite
  per `docs/citations.md` policy. Source filename:line attribution
  preserved on every entry; statistics and concepts unchanged. NIST,
  CISA, and Diamond Model quotes preserved verbatim (licence permits
  verbatim reproduction). ENISA Threat Landscape 2025 short quotes
  retained (CC BY 4.0). No code-path behaviour changes; documentation
  and JSON-string content only. Tracks task #122.

## [0.18.0] — 2026-05-24

Initiative G (IR Feedback Ingestion + Diamond Model Support) release —
paired with TRACE 1.11.0 + SAGE 0.13.0.

### Added

- **SAGE client `get_recent_incidents()`** (Phase 6, `2256ba5`):
  `src/beacon/sage/client.py` extended with own-org incident reader.
  Filters by `since`/`until`/`actor_stix_id`/`limit`. Bearer auth via
  `SAGE_API_AUTH_TOKEN` env (sent when set; absent header otherwise).
- **IR-observed Capability and Opportunity factors** (Phase 6,
  `2256ba5`): `CapabilityComponent` gains `ir_observed_capability:
  float = 1.0`; `OpportunityComponent` gains
  `ir_observed_opportunity: float = 1.0`. Both fields default to
  neutral 1.0 (identity in the geometric-mean aggregation) when SAGE
  is unreachable or skipped, so existing pipelines without SAGE
  produce unchanged outputs.

  Aggregation extended to 4-factor geometric means preserving the
  [0, 1] scale established in Initiative E:
  ```
  Depth       = (sophistication × tool_sophistication × evasion_capability × ir_observed_capability) ** (1/4)
  Opportunity = (victimology_match × geographic_match × surface_ttp_coverage × ir_observed_opportunity) ** (1/4)
  ```

  Boost logic per actor (when SAGE-fed incidents available):
  - `ir_observed_capability` = 1.0 if ≥1 own-org incident in
    lookback uses this actor's known TTPs; else 0.5 (neutral,
    not 0 — absence of own incidents should not zero out external
    attribution).
  - `ir_observed_opportunity` = 1.0 if actor ever attacked own org
    in lookback; else 0.7 (residual neutral — prior targeting is a
    strong Opportunity signal but no prior incident is not punitive).
- **`BEACON_IR_LOOKBACK_DAYS` env var** (Phase 6, `2256ba5`, default
  365): single global setting. Per-actor configurability deferred.
- **`--no-sage` flag in `cmd/generate_pir.py`** (Phase 6, `2256ba5`):
  bypasses SAGE call entirely (air-gapped / SAGE not deployed).
  Sets `data_quality.ir_boost_skipped=True` so caller can distinguish
  "deliberate skip" from "unintended degraded".
- **MITRE Cyber Prep methodology docstring extension in
  `actor_triage.py`** (Phase 6, `2256ba5`): notes that
  `ir_observed_capability` satisfies the "knowledge" element of
  Cyber Prep's Capability definition (Bodeau et al.) and
  `ir_observed_opportunity` satisfies the "how persistently the
  adversary targets a specific organization" element of Cyber Prep's
  Targeting.
- **Cross-repo `docs/ir-feedback-flow.md`** (Phase 8, `422d180`):
  relative symlink to `sage/docs/ir-feedback-flow.md` (authoritative
  source). Update once in SAGE, both BEACON and TRACE see the change.

### Changed (BREAKING)

- **`schema_version` bumped to `"0.18.0"`** in emitted PIR documents
  (Phase 6, `2256ba5`). TRACE 1.11.0 accepts `{"0.16.0", "0.17.0",
  "0.18.0"}`; consumers unable to upgrade must continue reading the
  prior versions.
- **`PIROutput` gains `mitre_attack_groups: list[str]` field**
  inherited from F Phase 2 (`718480f`) and populated via
  `source_matcher.resolve_group_ids(cluster.notable_groups)`.
- **`CapabilityComponent` and `OpportunityComponent` shape change**:
  4-factor geometric mean changes Likelihood numerics for actors with
  any IR-observed history. Schema_version gate enforces consumer
  ack.

### Fixed

- **`uv.lock` sync** (`ba65b61`): `name = "beacon", version = "..."`
  pinned to package version. Drift from earlier release commits
  surfaced during the task #122 audit.

## [0.17.0] — 2026-05-24

Initiative F (Temporal Window + Collection Plan + Summary API + RSS)
release — paired with TRACE 1.10.0 + SAGE 0.12.0.

### Added

- **Collection plan covers all P1-P4 priorities** (Phase 1, `ebabb3f`):
  `report_builder.collection_plan` now emits a unified document with
  every generated PIR (P1/P2) plus watch items (P3/P4) carrying
  priority badge, intelligence level, collection_focus, and a
  recommended-sources section.
- **MITRE ATT&CK source mapping derivation script** (Phase 1.6,
  `d57a76b`): `scripts/derive_source_groups.py` reads MITRE ATT&CK
  Enterprise STIX bundle ($ATTACK_BUNDLE_PATH, default
  `ref/enterprise-attack-19.1.json`), groups
  `intrusion-set.external_references` by `source_name`, and emits
  byte-deterministic `schema/source_attack_groups.derived.json`
  (1258 source entries). MITRE ATT&CK Terms of Use attribution
  preserved in derived JSON `_comment` field.
- **Multi-dimensional `content_ja.json` redesign** (Phase 1.7,
  `db5d593`): new `intelligence_requirements` (CU-GIR Framework
  decimal IDs + 5W1H EEI + mitre_attack_groups) and `sources` (tier +
  region + industry_focus + evidence_attack_groups + tlp +
  requires_membership + evidence_derivation) sections. Old flat
  `source_map` and `default_sources` removed. CU-GIR Framework
  decimal IDs reference Intel 471 CU-GIR (GitHub STIX JSON), under
  the Intel 471 CU-GIR Framework License (permits derivative works +
  distribution; preserves proprietary notices; prohibits competing
  CTI products — BEACON is open-source PIR tooling, not a CTI feed
  vendor).
- **`source_matcher.select_sources()` API** (Phase 1.7, `db5d593`):
  4-criterion intersection logic (tier ∈ intelligence_levels;
  org.region ∈ source.region ∪ {GLOBAL}; org.industry ∈
  industry_focus ∪ {cross-sector}; evidence_attack_groups ∩
  pir.mitre_attack_groups ≠ ∅ OR evidence_derivation =
  industry_consensus).
- **`docs/citations.md`** (Phase 1.7 + Phase 1.8): inventory of every
  external reference BEACON uses with license + attribution + usage
  policy. Covers MITRE ATT&CK, Intel 471 CU-GIR Framework, NIST SP
  family (800-30r1/37r2/53/61r3/82r3/161r1/207), MITRE Cyber Prep,
  Diamond Model paper, SANS, Verizon DBIR, IBM Cost-of-Data-Breach,
  ENISA, and other annual threat reports. Documents the 2026-05-23
  policy: external references must be cited (filename+line); verbatim
  text reproduction from proprietary reports is prohibited (paraphrase
  + attribution preferred). NIST docs and Diamond Model paper
  ("Approved for public release; distribution is unlimited") permit
  verbatim quotation; CC-BY-NC-ND CU-GIRH PDF handbook is explicitly
  NOT used.
- **MITRE Cyber Prep methodology citation in `actor_triage.py`**
  (Phase 1.8, `291f20b`): docstring extended to cite Bodeau et al.
  alongside existing SANS + NIST SP 800-30r1 citations, anchoring
  BEACON's `Likelihood = Intent × Capability × Opportunity` formula
  in MITRE's capability/intent/targeting framework. BEACON's
  `Opportunity` maps to MITRE Cyber Prep's `Targeting`.
- **`sources_yaml_builder.build_sources_candidate_yaml()`** (Phase 3,
  `7cd296e`): emits `output/sources_candidate.yaml` per-PIR with
  header annotations (tier/region/industry/evidence_attack_groups)
  and a top-of-file Capability-window warning. URL field is
  `<TODO: fill from candidate>` (operator-filled per F-2 decision).
  Operator manually merges into TRACE `input/sources.yaml` (does NOT
  overwrite). Output validates against TRACE `schema/sources.schema.json`.
- **`cmd/generate_pir.py --sources-candidate`** flag (Phase 3,
  `7cd296e`): wires `sources_candidate.yaml` emission after PIR
  generation.
- **`activity_window_days` config field** (Phase 5, `ecda9e0`):
  general BEACON-wide setting via `ACTIVITY_WINDOW_DAYS` env var
  (default 90). Operators set 180 in env to enable the 6-month
  trend workflow.

### Changed (BREAKING)

- **`CapabilityComponent.recency_active_campaigns_90d` →
  `recency_active_campaigns`** (Phase 5, `ecda9e0`): suffix dropped;
  window value now sourced from `ACTIVITY_WINDOW_DAYS` env var
  (default 90). No alias — schema_version gate enforces clean
  transition.
- **`schema_version` bumped to `"0.17.0"`** in emitted PIR documents.
  TRACE 1.10.0 validator accepts `{"0.16.0", "0.17.0"}`; consumers
  unable to upgrade must read the old name.
- **`schema/source_attack_groups.derived.json`** committed (auto-
  generated artifact, byte-deterministic).
- **`schema/content_ja.json` schema is a hard redesign**: callers
  reading `source_map` or `default_sources` will see KeyError /
  empty fallback. Use the new `intelligence_requirements` /
  `sources` sections + `source_matcher.select_sources()` API.

### Removed

- Legacy `_SOURCE_MAP` / `_DEFAULT_SOURCES` / `_SOURCES_PLACEHOLDER`
  constants from `generator/report_builder.py` (Phase 2, `718480f`).
  Use `source_matcher.select_sources()` instead.

## [0.16.0] — 2026-05-23

Initiative E (Actor Triage Phase 2) release — paired with TRACE 1.9.0 + SAGE 0.11.0.

### Added

- **Capability 6-factor scoring with Depth x Breadth aggregation**
  (Phase 1, 4fa9744): `CapabilityComponent` extended with 3 new sub-factors
  (`tool_sophistication`, `targeting_persistence`, `evasion_capability`) plus 2
  computed aggregates (`depth`, `breadth`). Aggregation:
  ```
  Depth   = (sophistication × tool_sophistication × evasion_capability)^(1/3)
  Breadth = (ttp_count_norm × targeting_persistence × recency_active_campaigns_90d)^(1/3)
  Capability = Depth × Breadth
  ```
  Same actor input now produces a different (more conservative) Likelihood
  value compared to 0.15.x. `update_taxonomy.py` extracts the new fields from
  MITRE ATT&CK STIX (campaign `first_seen` + count, defense-evasion TTP set).
  Golden regression tests lock numerics for APT28, APT41, Mustang Panda.

- **MISP cache refresh script** (Phase 2, 4afaf1f):
  `cmd/refresh_misp_cache.py` — idempotent atomic-write refresher for
  `beacon/cache/misp-threat-actor.json`. `docs/operations.md` documents
  cron entry, failure semantics, and alerting guidance.

- **`schema_version` top-level field** (Phase 3, cd11e30): `pir_output.json`
  now wraps PIR list in `PIROutputDocument` with required top-level
  `schema_version: "0.16.0"` field. Consumers MUST acknowledge schema
  version. Coordinated with TRACE 1.9.0 `from_payload` backward-compat path.

- **Web UI: `prioritized_actors` view and edit** (Phase 7, 96df7c4):
  `/review` shows top-5 `prioritized_actors` per PIR as collapsible cards
  with full sub-factor breakdown. `/review/save` accepts actor-level
  edits: exclude with reason, manual Likelihood override, append analyst
  rationale. `PrioritizedActor` gains 4 new fields: `excluded_by_analyst`,
  `exclusion_reason`, `manual_likelihood_override`,
  `analyst_rationale_append`. Edits persist in session; export reflects.

### Changed

- `schema_version` gate is a BREAKING change for direct PIR consumers:
  a bare `list[PIR]` is no longer the root shape. `PIROutputDocument` carries
  the list under `pirs`. TRACE 1.9.0 added backward-compat
  `from_payload` dispatch; other consumers must adapt similarly.
- Capability numerics shift due to Depth x Breadth aggregation. Same
  actor data → different Likelihood. Expected and documented.

### Fixed

(none — bug fixes shipped in 0.15.2 patch)

### Security

(none — security pin shipped in 0.15.2; `idna` and `starlette` pins inherited)

### Infrastructure

- `.githooks/pre-commit` exports `UV_CACHE_DIR` to handle sandbox env
  without writable global cache (Phase 7).

## [0.15.2] — 2026-05-23

### Security

- Pin `starlette>=1.0.1` (top-level) to address `PYSEC-2026-161`. The
  vulnerability is transitive via `fastapi`. Detected during the
  `pip-audit` step of Initiative E Phase 1 review on 2026-05-23.
  Co-shipped with SAGE 0.10.2 (same CVE, transitive via fastapi).
  TRACE is unaffected (no starlette/fastapi dependency).

## [0.15.1] — 2026-05-22

Security patch release.

### Security

- Pin `idna>=3.15` to mitigate CVE-2026-45409 (GHSA-65pc-fj4g-8rjx). The previous
  transitive resolution to idna 3.11 was vulnerable to specially crafted inputs that
  could bypass the CVE-2024-3651 fix.
- Paired security release: TRACE 1.8.1 + SAGE 0.10.1 ship the same patch.

## [0.15.0] — 2026-05-22

Paired release with TRACE 1.8.0 and SAGE 0.10.0.

### Added — actor triage (I × C × O likelihood scoring)

- **Actor triage core** (`src/beacon/analysis/actor_triage.py`):
  `Likelihood = Intent × Capability × Opportunity` (product form).
  Intent acts as a hard-gate: Intent = 0 excludes the actor from
  `prioritized_actors[]` entirely (not emitted with score 0).
  Sub-components are also product-form (plan §3.2 strict):
  `Intent = clip01(motivation_alignment × industry_match)`,
  `Capability = clip01(ttp_count_norm × sophistication_score × recency_active_campaigns_90d)`,
  `Opportunity = clip01(victimology_match × geographic_match × surface_ttp_coverage)`
  (Sign-off 2 revision — three-factor Opportunity, 2026-05-22).
- **MISP Galaxy client** (`src/beacon/ingest/misp_client.py`):
  `MispClient` with local-cache (offline/sandbox) primary path and
  optional live-MISP path via `pymisp` (optional dep, graceful on
  `ImportError`). `ActorAttributes` Pydantic model with STIX OV
  validation; invalid motivation/sophistication values normalize to
  `None` (no emission of invalid OV strings).
- **`schema/surface_ttp_map.json`**: SAGE asset-tag → MITRE ATT&CK
  Enterprise TTP mapping. 35 entries across 6 surfaces
  (external-facing, email_gateway, vpn_remote_access, cloud, ot,
  domain_controller). All entries cite `ref/` md sources with
  filename:line attribution (m-trends-2026-en.md,
  ENISA_Threat_Landscape_2025_v1.2.md,
  Dragos-2026-OT-Cybersecurity-Report-A-Year-in-Review.md).
- **MITRE ATT&CK STIX parser expansion** (`cmd/update_taxonomy.py`):
  `kill_chain_phases` extraction per attack-pattern, `software_count`
  and `technique_count` per group from `uses` relationships,
  `sophistication_tier` heuristic, `campaign_last_seen` via
  `attributed-to` relationships. New keys in `threat_taxonomy.json`:
  `intrusion_set_profiles` (189 entries) and `kill_chain_phases_map`
  (858 entries). Schema version bumped to `2.0.0`.
- **`prioritized_actors[]` in PIR output**
  (`src/beacon/generator/pir_builder.py`): top-level required field;
  `likelihood` is raw `[0, 1]` float (no rescale; UI display layer
  may ×100 separately). Pydantic `Field(ge=0.0, le=1.0)` constraints
  on `likelihood` and all 11 sub-factor floats.
- **`cmd/generate_schemas.py` — reproducible schema generation**:
  `sort_keys=True` + trailing newline produce byte-identical output
  on repeated invocations (idempotent; plan §7 Phase 4.5).
- `src/beacon/ingest/misp_client.py` declared as `[project.optional-
  dependencies] misp = ["pymisp>=2.4"]`.

### Changed

- **`risk_scorer`** (`src/beacon/analysis/risk_scorer.py`):
  accepts `top_actor_likelihood: float = 0.0`; applies `+1` boost to
  the base likelihood score when `top_actor_likelihood ≥ 0.05`
  (backward-compatible default = 0.0 → no change).
- **`pir_builder`** (`src/beacon/generator/pir_builder.py`):
  always emits `prioritized_actors[]` (empty array when no actors
  have Intent > 0 or triage is unavailable). Field is listed in
  top-level `required[]` of `pir_output.schema.json` via Pydantic
  `json_schema_extra` hook — no post-processing in
  `generate_schemas.py`.
- **`pir_output.schema.json`** regenerated from `PIROutput.model_json_schema()`.
  Now includes `$defs` for `PrioritizedActor`, `ScoreBreakdown`,
  `IntentComponent`, `CapabilityComponent`, `OpportunityComponent`,
  `DataQualityComponent`, and `Rationale`. Output is byte-deterministic.

### Citations / References

- **SANS I-O-C framework** (`ref/SANS_blog.md:L18`):
  "To understand, differentiate, and properly respond to threats, it is
  helpful to divide this concept into a further three components:
  Intent, Opportunity, and Capability (IOC)." BEACON applies this
  Threat-decomposition triad to compute a Likelihood-shaped actor
  priority score.
- **NIST SP 800-30 r1 Appendix D** (`ref/nistspecialpublication800-30r1.md:L1767–1768`):
  Table D-3 (Capability scale) and Table D-4 (Intent scale) inform
  the sub-factor normalization design.
- **STIX 2.1 open vocabularies**: `threat-actor-motivation-ov`
  (10 values) and `threat-actor-sophistication-ov` (7 values) are
  the only accepted inputs; invalid values normalize to `None`
  per `[[feedback_stix_strict_compliance]]`.

## [0.14.0] — 2026-05-13

### Added — three new business triggers (BEACON now has 10)

- `geopolitical_exposure` — fires when the organisation has HQ,
  operational presence, customer base, or supply-chain origin in a
  high-risk geopolitical zone (UA / RU / IL / PS / TW / CN / IR / KP /
  SY / YE). Backed by `GeopoliticalExposure` nested Pydantic model on
  `BusinessContext`. Absent block = no signal (does not fire). See
  `docs/triggers.md` §8 for the per-citation breakdown (CrowdStrike
  GTR 2025 / Cloudflare 2026 / IOCTA 2026 / INTERPOL ASP 2025-2026 /
  M-Trends 2026 Regional Breakouts).
- `ransomware_resilience_gap` — fires when the organisation cannot
  demonstrate ransomware-recovery readiness (missing backup posture /
  IR plan / fresh recovery test). Backed by `BusinessContinuity`
  nested model with `recovery_test_cadence_days ≤ 180` threshold.
  Absent block = conservative gap (fires). See `docs/triggers.md` §9
  (ENISA ETL 2025 / M-Trends 2026 "Ransomware is Now a Resilience
  Problem" / IBM CoDB 2025 / Dragos 2026 / CrowdStrike GTR 2025).
- `identity_credential_exposure` — fires when MFA coverage <95% OR
  PIM/PAM absent OR helpdesk authentication undocumented. Backed by
  `IdentityManagement` nested model. Absent block = conservative gap
  (fires). See `docs/triggers.md` §10 (CrowdStrike GTR 2025 valid
  account abuse 35% + vishing 442% / M-Trends 2026 cloud-vishing 23%
  / IOCTA 2026 IAB chapter / APWG Q4 2025 BEC).
- `HIGH_RISK_GEOPOLITICAL_ZONES` ISO 3166-1 alpha-2 frozenset (10
  entries) added to `src/beacon/analysis/element_extractor.py` with
  per-country rationale comments.
- `docs/triggers.md` + `docs/triggers.ja.md` extended with §8 / §9 /
  §10 sections including attributed `ref/` citations (file path + line
  number for each citation). Update procedure §1 now references the
  wider corpus (Cloudflare / IOCTA / APWG added) and a new step §4
  requires ref/-cited rationale for any `HIGH_RISK_GEOPOLITICAL_ZONES`
  revision.
- `schema/business_context.schema.json` regenerated to reflect the
  three new optional nested models on `BusinessContext`.
- `tests/test_element_extractor.py`: 18 new trigger cases across the
  three new triggers (default-fires-or-not, positive, boundary)
  plus 2 regression tests for the `_compute_likelihood` cap-5 boost
  rule with 10 active triggers.

### Notes

- Existing 0.13.x `context.json` payloads remain valid — all new
  schema fields are optional with safe defaults. The two new
  conservative-by-default triggers (`ransomware_resilience_gap`,
  `identity_credential_exposure`) WILL fire on legacy payloads that
  omit the new blocks; this is intentional (undocumented posture is
  treated as elevated risk per M-Trends 2026 framing).
- No existing trigger is removed or modified. `_HIGH_RISK_SECTORS`
  unchanged.
- Likelihood boost is still "+1 if any trigger fires, capped at 5".
  The cap holds with 10 triggers active and is regression-tested.

## [0.13.0] — 2026-05-13

### Added — Initiative C Phase 2 producer side

- `Identity` Pydantic model (`src/beacon/ingest/schema.py`) gains two
  optional fields, both with safe defaults so existing fixtures /
  `context.json` payloads remain valid without migration:
  - `is_high_value_impersonation_target: bool = False`
  - `impersonation_risk_factors: list[str] = []`
- LLM prompt `src/beacon/llm/prompts/context_structuring.md`:
  - Identities JSON schema block lists the two new fields.
  - New HLD §4.3 verbatim guidance under "Identities and Access"
    instructing the LLM to set the flag for publicly-recognizable
    brands, executive roles with public exposure (CFO/CEO/board), or
    critical suppliers whose name appears on customer-facing
    communications, and to populate `impersonation_risk_factors` with
    applicable tags (e.g. `['public-facing-brand', 'executive',
    'trusted-supplier']`).
- `src/beacon/analysis/identity_assets_generator.py`: propagate the two
  new fields into the emitted `identity_assets.json` so SAGE 0.9.0's
  `effective_priority` flag-first formula and TRACE 1.6.0's PIR L2 gate
  receive them.
- `schema/business_context.schema.json`: regenerated to reflect the
  expanded `Identity` model (additive only).
- `tests/fixtures/sample_identities_phase2.json`: new fixture
  demonstrating a flag-true executive identity alongside a flag-false
  default identity, used by the round-trip test.
- `tests/test_identity_assets_generator.py`: six new test cases under
  `TestImpersonationFlagPassThrough` covering flag pass-through,
  default behaviour, Pydantic validation of non-bool flag values,
  legacy-payload compatibility, and a fixture-loaded end-to-end
  round-trip.

## [0.12.3] — 2026-05-13

### Added

- `Makefile` target `check-pir-schema-drift`: compares `schema/pir_output.schema.json`
  against TRACE's `schema/pir.schema.json` using `scripts/check_pir_schema_drift.py`
  (TRACE-authored). Skips gracefully (warning, exit 0) when `../TRACE/` is not present.
  Chained into the `check` target.
- `Makefile` target `check-pir-roundtrip`: generates a PIR from
  `tests/fixtures/sample_context_manufacturing.json` via `cmd/generate_pir.py --no-llm`
  and validates the output with TRACE `cmd/validate_pir.py --strict`. Skips when
  `../TRACE/` is absent. Chained into the `check` target after `check-pir-schema-drift`.
- `tests/test_pir_roundtrip.py`: in-process round-trip unit test exercising
  `build_pirs()` → `PIROutput.model_dump_json()` → `PIRItem.model_validate()`.
  Uses the real `trace_engine.validate.schema.models.PIRItem` when TRACE is installed,
  otherwise falls back to an inline minimal replica so BEACON-only CI stays green.
- Updated `schema/pir_output.schema.json` to reflect current `PIROutput` model
  (added `organizational_scope`, `decision_point`, `recommended_action` as required
  fields; `notable_groups` as optional).
- `.githooks/pre-push`: appended explicit `make check-pir-schema-drift check-pir-roundtrip`
  call so the drift gate runs on every push.

### Docs

- Drop stale `Phase 2 onwards` framing on `google-genai` in
  `docs/dependencies.{md,ja.md}` — replaced with a concrete description
  pointing at the actual call site (`src/beacon/llm/client.py`).
- `src/beacon/ingest/context_parser.py`: drop `(Phase 2)` label from the
  markdown + `--no-llm` `NotImplementedError` message. The combination is
  intentionally unsupported (no future-implementation plan), so the
  Phase-2 marker only added confusion.
- `docs/triggers.{md,ja.md}`: 2026 annual review of the 7 business trigger
  citations against the expanded `ref/` corpus. Fixed three citation
  defects (T1 `cloud_dependency` M-Trends paraphrase not grep-verifiable;
  T3 `third_party_dependency` IBM "15% of breaches" not in IBM CoDB 2025
  and likely confused with DBIR prior-year stat; T6 `sectoral_high_risk`
  CrowdStrike sector list mismatch and dropped "China-nexus" qualifier).
  Added Dragos 2026 OT Cybersecurity Year in Review as the primary T2
  citation; added ENISA Finance Sectoral, International AI Safety Report
  2026, and Trend Micro AI-fication 2026 as additional T6 / T7 citations.
  No source-code or detection-logic change.

## [0.12.2] — 2026-05-10

### Fixed — `identity_class` aligned to STIX 2.1 §6.7 ``identity-class-ov``

Initiative A (BEACON 0.11.0) accepted ``"unspecified"`` as the
"genuinely ambiguous" `identity_class` value, but the canonical
STIX 2.1 §6.7 ``identity-class-ov`` value is ``"unknown"`` —
verified against ``stix2-validator``'s
``IDENTITY_CLASS_OV`` (and the same is true of STIX 2.0). The
mistake propagated through Pydantic Literal, the
``context_structuring`` LLM prompt, and the analyst-facing
``context_template.{md,ja.md}`` since 0.11.0.

The downstream STIX validator therefore issued one ``{213}``
warning per ``identity_class: "unspecified"`` SDO at TRACE bundle
emission time. TRACE 1.4.2 real-LLM crawl on the Trend Micro
article surfaced exactly one such warning, which closed out the
verification: identical structural class to ``{244}``, just on a
different vocabulary.

#### Changes

- `UserAccount` is unaffected; this only touches `Identity`.
- `Identity.identity_class` Pydantic Literal: `unspecified` → `unknown`.
- `context_structuring.md` LLM prompt: same correction in both
  the JSON schema block and the per-class guidance bullet
  ("`unknown` when the document is genuinely ambiguous").
- `docs/context_template.md` / `context_template.ja.md`: same.

#### Migration

User-managed `BEACON/input/context.md` should rename any
`identity_class: unspecified` to `identity_class: unknown`. The
in-house e-money pilot fixture in this repo had no such
occurrence (verified by grep).

Pairs with TRACE 1.4.3. SAGE 0.7.0 schema unchanged (DDL comment
updated to STIX-canonical wording — no functional change since
`identity_class` is `STRING(32)`).

---

## [0.12.1] — 2026-05-10

### Changed — `account_type` aligned to STIX 2.1 §6.4 ``account-type-ov`` strictly

Initial 0.12.0 emitted operationally-named values (`service`,
`unix-account`, `azure-ad`, `google-workspace`, `saas`,
`kerberos`, `other`) that are not present in STIX 2.1 §6.4
``account-type-ov``. The downstream STIX validator therefore
issued one `{244}` warning per non-spec value at TRACE bundle
emission time.

We are committed to honouring the STIX vocabulary instead of
extending it; otherwise the rationale for using STIX evaporates.

`UserAccount.account_type` Pydantic Literal now restricts values
to the canonical 12-member STIX OV plus empty string:

```
"" | unix | windows-local | windows-domain | ldap | tacacs |
radius | nis | openid | facebook | skype | twitter | kavi
```

`""` is the default and represents *"no STIX value applies"*.
Operational distinctions move to:

- `is_service_account: bool` (STIX 2.1 §6.4 native property) for
  service / automation accounts.
- `description` for free-form context (e.g. "Azure AD tenant
  contoso.onmicrosoft.com") when STIX has no suitable
  `account_type` value.

#### Migration (existing `user_accounts.json`)

Hand-edit existing `BEACON/input/context.md` user-account entries:

| Was | Becomes |
|---|---|
| `unix-account` | `unix` (rename to spec value) |
| `service` | `""` + ensure `is_service_account: true` |
| `other` | `""` |
| `azure-ad` / `google-workspace` / `saas` / `kerberos` | `""`; add note in `description` |

LLM prompt (`context_structuring.md`) updated to instruct the
extractor to emit only STIX OV values or empty string.

Pairs with TRACE 1.4.2 (matching extractor + bundle assembler).
SAGE 0.7.0 schema is unchanged (STRING(64) accepts both OV
values and NULL/empty).

---

## [0.12.0] — 2026-05-10

### Added — Initiative B: User-Account SCO artifact

First slice of the User-Account SCO initiative (paired with TRACE
1.3.0 + SAGE 0.7.0 to follow). BEACON emits a new
`user_accounts.json` artifact: individual login identifiers
(`alice@corp`, `svc-jenkins`, domain SIDs, cloud principals) plus
their host-asset bindings.

Motivation grounded in published frameworks (full citations in the
local Initiative B design doc):

- NIST SP 800-53 R5 IA-2 / IA-4 / AC-2 — per-account inventory
- NIST SP 800-63B — authenticator binding to subscriber
- ISO/IEC 27001:2022 A.5.16 / A.8.5 — identity / authentication lifecycle
- CIS Controls v8 #5 — account inventory & privileged separation

Empirical reinforcement (past 12 months):

- Verizon DBIR 2025: stolen credentials = #1 initial-access (22%)
- CrowdStrike GTR 2025: valid-account abuse = #1 cloud vector (35%)
- Mandiant M-Trends 2026: privileged accounts in 60%+ of post-
  compromise lateral movement

Initiative A captured Identity ↔ Asset role-level access; Initiative
B drops one level deeper to per-account granularity so analysts can
trace specific credential theft impact.

#### Schema additions

`src/beacon/ingest/schema.py`:

- `UserAccount` — `id`, `account_login`, `display_name`,
  `account_type` (Literal of STIX 2.1 §6.4 `account-type-ov`:
  unix-account / windows-local / windows-domain / ldap / kerberos /
  azure-ad / google-workspace / saas / service / other),
  `is_privileged`, `is_service_account`, `identity_id` (optional
  FK), `description`.
- `AccountOnAsset` — `user_account_id`, `asset_id`, `first_seen`,
  `last_seen`. Composite key (account, host); same login on two
  hosts produces two edges.
- `BusinessContext` extended with `user_accounts[]` and
  `account_on_asset[]` (both default to empty list).

#### `cmd/generate_user_accounts.py` (new CLI)

Mirrors `generate_identity_assets.py`. Reads context.md or
context.json, emits `output/user_accounts.json`. Same `--no-llm`
JSON-only path. Output `_comment` directs the user to TRACE's
`validate_user_accounts.py` (TRACE 1.3.0).

#### Asset id normalization (Initiative A 0.11.1 lesson applied)

`account_on_asset[*].asset_id` runs through the same
`_normalize_asset_id` (`asset-` prefix) used by
`assets_generator.py` and `identity_assets_generator.py`. Without
this, TRACE's cross-ref would reject every edge as dangling. Test
explicitly guards the normalization (`test_asset_id_normalized_to_asset_prefix`).

#### LLM prompt extension

`src/beacon/llm/prompts/context_structuring.md` adds:

- `user_accounts[]` and `account_on_asset[]` to the schema block
- "User Accounts / Login Accounts / Service Accounts" entry in the
  Section Recognition Guide
- New "User Accounts and Asset Mapping" mapping rules with
  `account_type` inference, `is_privileged` / `is_service_account`
  guidance, and the no-fabrication rule

#### `context_template.{md,ja.md}` extension

New "User Accounts" section with granularity guide, account /
account-on-asset entry templates, and a worked example based on
the in-house e-money pilot fixture.

### Tests

11 new cases in `tests/test_user_accounts_generator.py`:

- empty-context emits empty arrays
- single account / service account / privileged flags
- AccountOnAsset edge with first_seen
- asset_id normalization (`CA-005` → `asset-CA-005`)
- already-prefixed pass-through
- same login on two hosts → two edges
- dangling user_account_id passes through (cross-ref is TRACE's job)
- defaults

All 286 tests pass; 0 vulnerabilities.

### Pairing

Requires TRACE 1.3.0 (validator + extractor) + SAGE 0.7.0 (schema +
ingest + mapper) for end-to-end value. BEACON 0.12.0 standalone
emits a valid artifact but no consumer until those land.

---

## [0.11.1] — 2026-05-10

### Fixed — `identity_assets.json` asset_id normalization mismatch

E2E verification of Initiative A surfaced that
`identity_assets_generator.py` was emitting `has_access[*].asset_id`
in the LLM-extracted raw form (e.g. ``CA-001``) while
`assets_generator.py` normalizes the same id to ``asset-CA-001`` via
`_normalize_asset_id`. TRACE 1.1.0+ validate_identity_assets
performs string-equality cross-reference between the two artifacts,
so every `has_access` edge was rejected as a dangling reference.

The fix imports `_normalize_asset_id` from `assets_generator` and
applies it in the identity_assets builder. Both BEACON outputs now
share a single id form (`asset-<original>`); the TRACE cross-ref
check resolves cleanly; SAGE's `load_identity_assets` continues to
re-normalize defensively for inputs from other sources (idempotent).

### Tests

3 new cases in `tests/test_identity_assets_generator.py::TestAssetIdNormalization`:

- raw `CA-001` gets `asset-` prefix
- already-prefixed id passes through unchanged
- output is idempotent under repeat normalization (SAGE's defense
  layer doesn't double-prefix)

All 275 tests pass; 0 vulnerabilities.

---

## [0.11.0] — 2026-05-10

### Added — Initiative A: Identity-Asset HasAccess artifact

First slice of the 3-project Identity-Asset HasAccess initiative
(see local design doc for the full plan). BEACON now emits a new
`identity_assets.json` artifact that describes which roles, groups,
or individuals have access to which `critical_assets` — the input
SAGE 0.6.0 will ingest as `Identity` SDOs and `HasAccess` edges,
with TRACE 1.1.0 as the validation gate.

Motivation grounded in published frameworks:

- **NIST SP 800-53 R5** AC-2 (Account Management), AC-3 (Access
  Enforcement) — accounts and their resource rights must be
  documented and reviewed.
- **NIST SP 800-207** Zero Trust — explicit identity-to-resource
  mapping is a precondition for dynamic policy.
- **ISO/IEC 27001:2022** A.5.16, A.5.18 — full lifecycle of
  role-based access rights to information assets.
- **CIS Controls v8** Controls 5, 6 — inventory and manage accounts
  and access rights to enterprise assets.

Empirical reinforcement (past 12 months):

- Verizon DBIR 2025: stolen credentials = #1 initial-access (22%)
- CrowdStrike GTR 2025: valid-account abuse = #1 cloud vector (35%)

Without an identity-asset edge SAGE cannot answer "which assets are
exposed when role X is compromised" — the dominant analyst question
after a credential theft.

#### Schema additions

`src/beacon/ingest/schema.py`:

- `Identity` — `id`, `name`, `identity_class` (STIX 2.1 §6.7
  open vocab: individual / group / system / organization / class /
  unspecified), `sectors[]`, `roles[]`, `description`. Granularity
  decision (2026-05-10): role / group primary, individuals optional.
- `HasAccess` — `identity_id`, `asset_id`, `access_level`
  (read / write / admin / deny), `role` (per-edge label),
  `granted_at`, `revoked_at`.
- `BusinessContext` extended with `identities[]` and `has_access[]`
  (both default to empty list).

#### `cmd/generate_identity_assets.py` (new CLI)

Mirrors `generate_assets.py`. Reads context.md or context.json,
emits `output/identity_assets.json`. Same `--no-llm` semantics
(JSON-only). The output includes a `_comment` directing the user to
TRACE's `validate_identity_assets.py` before SAGE ingest.

#### LLM prompt extension

`src/beacon/llm/prompts/context_structuring.md` updated:

- Schema block adds `identities[]` and `has_access[]`.
- "Section Recognition Guide" maps "Identities and Access / Roles /
  Teams with Access / RBAC" → `identities[]` + `has_access[]`.
- New "Identities and Access" mapping rules with `identity_class`
  inference, `id` slug convention, `access_level` keyword mapping
  (admin / write / read / deny), and the no-fabrication rule (return
  empty arrays when the section is absent).

The expanded output stays within the existing 32k token budget
(0.10.2): the in-house e-money pilot context produces ~7k chars
of structured JSON even before this addition; identity sections
add a few hundred chars per identity at most.

#### `_comment` field on output

The generated `identity_assets.json` carries a `_comment` directing
the user to validate via TRACE before loading into SAGE (matches
the `assets.json` UX from BEACON 0.6.0).

#### No cross-reference validation here

The generator does **not** verify that `has_access[*].identity_id`
points to an existing `identities[*].id`, or that
`has_access[*].asset_id` points to an existing
`critical_assets[*].id`. That responsibility belongs to TRACE's
`validate_identity_assets.py` (Initiative A §6.1) which has the
adjacent `assets.json` to cross-check against.

### Tests

9 new cases in `tests/test_identity_assets_generator.py`:

- empty-context emits empty-array (not missing-key) artifact
- single identity round-trip (Japanese name, identity_class,
  sectors / roles)
- single HasAccess edge with full optional fields
- dangling `identity_id` passes through unraised (cross-ref is
  TRACE's job, not the generator's)
- optional-field defaults

All 272 tests pass; 0 vulnerabilities.

### Future scope (BEACON share of remaining Initiative A)

- Phase 2 (post-production data review): surface identities tagged
  `privileged` for PIR weighting in SAGE.
- in-house e-money pilot `context.md` upgrade: add an
  "Identities and Access" section so the next regeneration
  populates real edges (currently the section is absent → empty
  arrays).

---

## [0.10.2] — 2026-05-10

### Fixed — `context_structuring` JSON truncation on long ja-JP contexts

`cmd/generate_assets.py` failed mid-pipeline against the in-house
e-money pilot context.md (6619 chars input) with
`json.JSONDecodeError: Unterminated string`. The LLM emitted ~6890
chars of valid JSON before the response cut off in the middle of an
asset's `data_types` array — i.e. the response hit the
`max_output_tokens` ceiling.

Root cause: `call_llm` had a hard-coded default
`max_output_tokens=8192`, and `context_structuring` is the largest
single-call output BEACON makes — input scales linearly into output
size, and ja-JP characters cost more tokens than English. The 8192
default was sized for early Phase 1/2 inputs and never re-tuned for
the current detail level.

#### Per-tier output token budgets in Config

Three new Config fields (env-overridable):

| Field | Env var | Default |
|-------|---------|---------|
| `llm_max_output_tokens_simple` | `BEACON_LLM_MAX_OUTPUT_SIMPLE` | 32768 |
| `llm_max_output_tokens_medium` | `BEACON_LLM_MAX_OUTPUT_MEDIUM` | 32768 |
| `llm_max_output_tokens_complex` | `BEACON_LLM_MAX_OUTPUT_COMPLEX` | 32768 |

`call_llm` now resolves the budget through `_max_output_for_task`
by default; passing `max_output_tokens=` explicitly still overrides
it (used by tests). The `llm_call_start` log line now includes
`max_output_tokens` for diagnostics.

Why per-tier instead of a single dial: the three tiers do
materially different work (markdown→JSON, threat tag enrichment,
likelihood scoring), and we want to be able to expand or contract
each independently without coupling them.

Why default 32768: gemini-2.5-flash supports up to 65536 output
tokens. context_structuring on the in-house e-money pilot context
produces ~6k output tokens, so 32k gives ~5x headroom for
context.md files that grow over time. We did not pick 65536 to
keep latency / cost bounded on the common path.

### Documented — `.env.example`

Three new commented-out env vars added with usage notes ("bump if
context.md is materially larger or truncation reappears").

### Tests

3 new cases in `tests/test_llm_client.py::TestMaxOutputTokens`:

- per-tier budget read from Config (24k / 48k / 64k matrix)
- explicit `max_output_tokens=` argument overrides Config
- callers that omit the argument inherit the per-tier Config budget
  (regression guard for `parse_markdown` / `threat_mapper` etc.)

All 263 tests pass; 0 vulnerabilities.

---

## [0.10.1] — 2026-05-09

### Removed — Deprecation stubs deleted

`cmd/stix_from_report.py` and `cmd/validate_pir.py` were retained as
deprecation stubs in 0.9.0 with the explicit promise that they would
be removed in 0.10.0. The 0.10.0 trigger refactor missed that cleanup;
0.10.1 finishes the migration.

Both stubs simply printed a "moved to TRACE" message and pointed users
at `TRACE/cmd/crawl_single.py` and `TRACE/cmd/validate_pir.py`
respectively. There is no behavioural change for any caller — the
stubs were already non-functional.

### Migration

Anyone who was still invoking the BEACON-side commands needs to switch
to TRACE:

- `BEACON/cmd/stix_from_report.py …` → `cd TRACE && uv run python cmd/crawl_single.py …`
- `BEACON/cmd/validate_pir.py …` → `cd TRACE && uv run python cmd/validate_pir.py …`

---

## [0.10.0] — 2026-05-09

### Changed (BREAKING) — Business trigger framework rebuilt around NIST SP 800-37 R2

The previous five triggers (`ot_connectivity`, `cloud_migration`, `m_and_a`,
`ipo_or_listing`, `supply_chain_expansion`) and the asymmetric high-risk
subset `{ot_connectivity, m_and_a, ipo_or_listing}` lacked external
citation — they were BEACON-internal heuristics that could not be defended
to a third-party auditor. The trigger set has been rebuilt around the NIST
SP 800-37 Rev 2 *Event-Driven Triggers / Significant Changes to the
Environment of Operation* framework, with each trigger corroborated by at
least one long-standing standard (NIST/ISO/IEC/SEC/EU) **or** two or more
independent past-12-month incident-response reports.

**New trigger vocabulary** (replaces the five old strings — any consumer
reading `active_triggers[*]` must update):

| New trigger | Primary citation |
|-------------|-----------------|
| `cloud_dependency` | CISA Cloud Security TRA v2; CrowdStrike GTR 2025; M-Trends 2026 |
| `it_ot_convergence` | NIST SP 800-82 R3; ENISA ETL 2025; IEC 62443 |
| `third_party_dependency` | NIST SP 800-161 R1; Verizon DBIR 2025 (third-party 30%); IBM CoDB 2025 |
| `external_facing_exposure` | Mandiant M-Trends 2026 (#1: 32%); Verizon DBIR 2025; CISA KEV |
| `regulated_disclosure_scope` | SEC Final Rule 33-11216 Item 106; EU NIS2 Art. 23; HIPAA Breach Notification |
| `sectoral_high_risk` | ENISA ETL 2025; Verizon DBIR 2025; CrowdStrike GTR 2025 |
| `ai_adoption_exposure` | IBM CoDB 2025 ($670K shadow-AI premium, 63% no governance); CrowdStrike GTR 2025; ENISA ETL 2025 |

**Removed trigger:** `m_and_a_integration` was considered but dropped because
its empirical support in past-12-month reports was substantially weaker than
the seven retained triggers; SEC Reg S-K Item 105 alone is insufficient to
sustain the citation contract.

### Removed — `high_risk_triggers` asymmetric subset

`{ot_connectivity, m_and_a, ipo_or_listing}` was singled out for likelihood
boost and operational-level escalation in `risk_scorer._compute_likelihood`
and `_recommend_level`. NIST SP 800-37 R2 does not differentiate event-driven
trigger weights, so the subset was indefensible as a scoring asymmetry.
Replaced with symmetric handling: any active trigger contributes `+1` to
likelihood (capped at 5) and lifts `tactical → operational`.

### Changed — Detection prefers BusinessContext structural fields

`element_extractor._detect_triggers` now derives most triggers from typed
Pydantic fields — `network_zone`, `exposure_risk`, `managing_vendor`,
`industry`, `regulatory_context` — rather than fragile keyword matching.
Keyword matching is restricted to:

- `ai_adoption_exposure` (AI/ML/LLM vocabulary)
- `regulated_disclosure_scope` fallback (regulation names not captured by
  `stock_listed`)

The previous `m_and_a` keyword path and `expansion_keywords` set are
removed from `schema/trigger_keywords.json`.

### Added — `docs/triggers.md` and `docs/triggers.ja.md`

Canonical per-trigger definition, detection logic, citation table, weighting
rationale, and annual update procedure. The previous trigger framing was
spread across `risk_scorer.py` comments, `high-level-design.md` §5.3, and
`data-model.md`, with no single source of truth and no citation block.

### Added — `_HIGH_RISK_SECTORS` constant in `element_extractor.py`

Empirical intersection of sector-level targeting evidence from ENISA Threat
Landscape 2025, Verizon DBIR 2025, and CrowdStrike Global Threat Report
2025: `{finance, healthcare, energy, manufacturing, government, defense,
logistics, technology}`. Drives the `sectoral_high_risk` trigger.
Update cadence: annually when those reports' next editions publish.

### Documentation

- `high-level-design.md` §5.3 rewritten to reference the seven-trigger set
  and `docs/triggers.md` rather than the deprecated subset.
- `docs/data-model.md` and `.ja.md` updated to remove the M&A/OT/IPO
  hardcoded enumeration and link to the new triggers document.
- `schema/content_ja.json` `trigger_actions` keys remapped from the five
  old strings to the seven new ones, with collection-action descriptions
  citing the empirical sources.

### Migration

Any downstream system reading `pir_output.json[*].active_triggers` must
update its vocabulary. Specifically: TRACE consumes
`x_trace_matched_pir_ids` and the PIR list itself but does not currently
gate on trigger string values. SAGE ingests PIR documents but does not
filter on trigger strings either. No SAGE/TRACE schema change is required;
the trigger value field is informational metadata in both consumers.

---

## [0.9.0] — 2026-05-08

### Security

- Bumped `python-multipart` to `>=0.0.27` (CVE-2026-42561).
- Pinned `pip>=26.1` in dev extras to address CVE-2026-6357 in the
  transitive `pip-api` → `pip` chain pulled by `pip-audit`. CVE-2026-3219
  (also in `pip`) has no fix release as of this version; tracked upstream.

### Removed — URL/PDF → STIX extraction moved to TRACE

The URL/PDF → STIX 2.1 extraction pipeline has been transferred to the new
sibling project **TRACE** (Threat Report Analyzer & Crawling Engine) at
`/Users/test/Projects/claude_pj/TRACE/`. BEACON now focuses on internal
context (assets, PIR) generation only.

- Removed `src/beacon/ingest/stix_extractor.py` (→ `TRACE/src/trace_engine/stix/extractor.py`)
- Removed `src/beacon/ingest/report_reader.py` (→ `TRACE/src/trace_engine/ingest/report_reader.py`)
- Removed `src/beacon/llm/prompts/stix_extraction.md` (→ `TRACE/src/trace_engine/llm/prompts/stix_extraction.md`)
- Removed corresponding tests `tests/test_stix_extractor.py`, `tests/test_report_reader.py`
- Removed `markitdown[pdf]` dependency (only used by the migrated code)
- `cmd/stix_from_report.py` is now a deprecation stub directing users to
  `TRACE/cmd/crawl_single.py`. The stub will be deleted in 0.10.0.
- `cmd/validate_pir.py` is now a deprecation stub directing users to
  `TRACE/cmd/validate_pir.py`, which adds referential checks (taxonomy
  presence, asset-tag match, validity window) on top of the schema check
  this command previously performed. The stub will be deleted in 0.10.0.

Output artifact schemas (`assets.json`, `pir_output.json`) are unchanged;
this is a minor bump because the public CLI surface that BEACON owns is
unchanged. The removed CLI was an analyst-facing utility, not a stable
contract — its replacement lives in TRACE.

See `TRACE/docs/beacon_handoff.md` for the full migration note.

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
