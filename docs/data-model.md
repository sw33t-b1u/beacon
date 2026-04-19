# BEACON — Data Model

Japanese translation: [`docs/data-model.ja.md`](data-model.ja.md)

## Input: BusinessContext JSON

Place your strategy document as `input/context.md` (see [`docs/context_template.md`](context_template.md)).
The LLM converts it to a structured `BusinessContext`; use `--save-context` to inspect the intermediate JSON.

```json
{
  "organization": {
    "name": "Example Corp",
    "industry": "manufacturing",
    "geography": ["Japan", "Southeast Asia"],
    "stock_listed": true,
    "regulatory_context": ["APPI", "ISO27001"]
  },
  "crown_jewels": [
    {
      "id": "CJ-001",
      "name": "Product Design Data (CAD)",
      "system": "PLM system",
      "business_impact": "critical",
      "exposure_risk": "medium"
    }
  ],
  "critical_assets": [
    {
      "id": "CA-001",
      "name": "SAP ERP Production",
      "type": "application",
      "function": "Core ERP for finance and manufacturing operations",
      "hostname": "sap-prod-01",
      "os_platform": "SLES 15",
      "network_zone": "corporate",
      "criticality": "critical",
      "data_types": ["financial", "pii"],
      "managing_vendor": "SAP SE",
      "supply_chain_role": "",
      "dependencies": ["CA-002"],
      "exposure_risk": "medium"
    }
  ],
  "supply_chain": {
    "ot_connectivity": true,
    "cloud_providers": ["GCP"]
  }
}
```

### CriticalAsset fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique asset identifier (e.g. `CA-001`) |
| `name` | string | Human-readable asset name |
| `type` | enum | `server`, `database`, `network_device`, `application`, `endpoint`, `storage`, `identity_system`, `ot_device`, `cloud_service`, `other` |
| `function` | string | Business function description (used for keyword-based tag matching) |
| `hostname` | string | Hostname or FQDN (optional) |
| `os_platform` | string | OS or platform (optional) |
| `network_zone` | enum | `internet`, `dmz`, `corporate`, `ot`, `cloud`, `restricted`, `unknown` |
| `criticality` | enum | `low`, `medium`, `high`, `critical` |
| `data_types` | list[string] | Data types stored/processed (e.g. `pii`, `financial`, `phi`) |
| `managing_vendor` | string | Vendor responsible for the asset (used as active vendor signal) |
| `supply_chain_role` | string | Role in supply chain (e.g. `tier1-supplier-gateway`) |
| `dependencies` | list[string] | Asset IDs this asset depends on |
| `exposure_risk` | enum | `low`, `medium`, `high`, `critical` |

Full schema: `schema/business_context.schema.json` (generate with `uv run python cmd/generate_schemas.py`)

---

## Output: PIR JSON (SAGE-compatible)

```json
[
  {
    "pir_id": "PIR-2026-001",
    "intelligence_level": "strategic",
    "description": "Strengthen defenses against threat actors targeting manufacturing×Japan crown jewels (PLM system)",
    "rationale": "Likelihood=5, Impact=5 — Industry/geography match: state_sponsored.China, ransomware / OT connectivity — lateral movement risk",
    "threat_actor_tags": ["apt-china", "espionage", "ip-theft", "ot-targeting", "ransomware"],
    "asset_weight_rules": [
      { "tag": "plm", "criticality_multiplier": 2.5 },
      { "tag": "ot",  "criticality_multiplier": 2.0 }
    ],
    "collection_focus": [
      "Monitor new TTPs and infrastructure changes: MirrorFace / APT10",
      "Vulnerability exploitation targeting OT/ICS environments"
    ],
    "valid_from": "2026-04-04",
    "valid_until": "2027-04-04",
    "risk_score": { "likelihood": 5, "impact": 5, "composite": 25 }
  }
]
```

Full schema: `schema/pir_output.schema.json` (generate with `uv run python cmd/generate_schemas.py`)

> **Note:** `--no-llm` mode produces English output as shown above. When LLM augmentation is enabled (default), `description`, `rationale`, and `collection_focus` are rewritten by Vertex AI Gemini and may be in the organization's language context.

---

## PIR Priority Filtering

Only P1 and P2 are included in `pir_output.json`. P3 items are tracked in `collection_plan.md` (generated with `--collection-plan`).

| Priority | Composite score | Typical example |
|----------|-----------------|-----------------|
| P1 | ≥ 20 | Nation-state APT targeting industry crown jewels |
| P2 | 12–19 | Active ransomware campaign against the sector |
| P3 (plan only) | 1–11 | Generic CVE advisory with low industry relevance |

---

## Collection Plan (collection_plan.md)

`collection_plan.md` is a Markdown report generated alongside `pir_output.json`. It captures items that did not make the P1/P2 threshold and serves as the CTI team's operational collection schedule.

**Generated with:**

```bash
uv run python cmd/generate_pir.py --context ... --output pir_output.json \
  --collection-plan collection_plan.md
```

**Contents:**

| Section | Description |
|---------|-------------|
| P3 watch items | Threats below the P2 threshold; monitor but do not act immediately |
| Trigger-based actions | Collection actions triggered by business events (M&A, OT expansion, IPO) |
| Collection frequency table | Monthly / weekly / daily schedule per feed type for the CTI team |

`collection_plan.md` is listed in `.gitignore` (runtime output; not committed).

---

## Intelligence Level & Validity

| Level | Composite | valid_until | Example |
|-------|-----------|-------------|---------|
| `strategic` | 20–25 | +12 months | Nation-state APT targeting industry IP |
| `operational` | 12–19 | +6 months | Active ransomware campaign |
| `tactical` | 1–11 | +1 month | Specific CVE exploitation |

Business triggers (M&A, OT connectivity, IPO) can escalate `tactical` → `operational` regardless of score.

---

## LLM Integration (Vertex AI Gemini)

| Step | Trigger | Model |
|------|---------|-------|
| MD → BusinessContext (`parse_markdown`) | `.md` input | `gemini-2.5-flash-lite` |
| Threat tag completion (`map_threats`) | Dictionary: 0 matches | `gemini-2.5-flash-lite` |
| PIR text augmentation (`build_pirs`) | `use_llm=True` always | `gemini-2.5-flash` |
| Likelihood scoring assist (`score`) | Dictionary: no basis | `gemini-2.5-pro` |

Authentication uses Application Default Credentials (ADC). No API key management required.

---

## Threat Taxonomy Coverage

`schema/threat_taxonomy.json` is fully auto-generated from two sources:

- **MITRE ATT&CK Enterprise** (`intrusion-set`, `attack-pattern`, `uses` relationships) — canonical group names and priority TTPs.
- **MISP Galaxy `threat-actor` cluster** (`cfr-suspected-state-sponsor`, `cfr-type-of-incident`, `cfr-suspected-victims`, `country`) — state-sponsor attribution, non-state motivation, target industries/geographies.

Category axes:

| Axis | Buckets |
|------|---------|
| `state_sponsored.<Country>` | Canonical country names from MISP `cfr-suspected-state-sponsor` (e.g., China, Russia, North Korea, Iran, India, South Korea, Vietnam, United States). Aliases normalized (e.g., `USA` → `United States`). |
| Non-state | `espionage`, `financial_crime`, `sabotage`, `subversion` — derived from MISP `cfr-type-of-incident`. |

Each bucket carries:

- `tags` — short labels like `apt-china`, `financial-crime` (state buckets get `apt-<country-slug>`).
- `mitre_groups` — canonical names from MITRE ATT&CK.
- `priority_ttps` — MITRE technique IDs linked via `uses` relationships.
- `target_industries` — MISP coarse vocabulary (`Private sector`, `Government`, `Military`, `Civil society`).
- `target_geographies` — MISP `cfr-suspected-victims` country list.

**Industry matching** uses a BEACON-to-MISP coarse mapping (`threat_mapper._BEACON_TO_MISP_INDUSTRY`):

| BEACON industry | MISP category |
|-----------------|--------------|
| defense | Military |
| government | Government |
| education | Civil society |
| manufacturing, finance, energy, healthcare, technology, logistics, other | Private sector |

**Geography matching** treats empty `target_geographies` and `Global` as "accept all"; otherwise the organization's geography must overlap.

Regenerate the taxonomy from the authoritative feeds:

```bash
uv run python cmd/update_taxonomy.py [--dry-run]
```

`_metadata.sources` in the JSON records the canonical fetch URLs. No manual curation layer exists — all content comes from the two upstream feeds, which lets `update_taxonomy.py` rebuild the file deterministically.
