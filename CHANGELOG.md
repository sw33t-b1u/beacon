# BEACON Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/). Versioning follows [Semantic Versioning](https://semver.org/).

---

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
楽天Edy fixture in this repo had no such occurrence (verified by
grep).

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
account-on-asset entry templates, and a worked 楽天Edy-style
example.

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
(0.10.2): the 楽天Edy context produces ~7k chars of structured JSON
even before this addition; identity sections add a few hundred
chars per identity at most.

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
- 楽天Edy `context.md` upgrade: add an "Identities and Access"
  section so the next regeneration populates real edges (currently
  the section is absent → empty arrays).

---

## [0.10.2] — 2026-05-10

### Fixed — `context_structuring` JSON truncation on long ja-JP contexts

`cmd/generate_assets.py` failed mid-pipeline against the 楽天Edy
context.md (6619 chars input) with
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
tokens. context_structuring on the 楽天Edy context produces ~6k
output tokens, so 32k gives ~5x headroom for context.md files that
grow over time. We did not pick 65536 to keep latency / cost bounded
on the common path.

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
