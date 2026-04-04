# BEACON

**Business Environment Assessment for CTI Organizational Needs**

BEACON converts organizational business context (JSON or Markdown strategy documents) into [SAGE](../SAGE)-compatible **Priority Intelligence Requirements (PIR) JSON** using a dictionary-based pipeline augmented by Vertex AI Gemini.

> PIRs are the "information requirements that security needs to protect the business." BEACON bridges the gap between business strategy and CTI prioritization.

---

## Overview

```
[business_context.json / strategy.md]
            │
            ▼
     BEACON PIPELINE
  ┌──────────────────────┐
  │ Step 1: Element Ext. │  strategic objectives, projects, crown jewels
  │ Step 2: Asset Map    │  → SAGE asset tags (plm, ot, cloud, erp …)
  │ Step 3: Threat Map   │  industry × geography → threat actor tags
  │ Step 4: Risk Score   │  Likelihood × Impact (1–5 scale)
  │ Step 5: PIR Build    │  SAGE-compatible PIR JSON
  └──────────────────────┘
            │
            ▼
    [pir_output.json]  →  SAGE ETL  →  pir_adjusted_criticality
```

**Two modes:**

| Mode | Input | LLM | Use case |
|------|-------|-----|----------|
| `--no-llm` | JSON only | None | Air-gapped / cost-constrained |
| Default | JSON or Markdown | Vertex AI Gemini | Full quality |

---

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- GCP project with Vertex AI API enabled (for LLM mode)

### Setup

```bash
cd BEACON
uv sync
```

### Generate PIR (dictionary-only mode)

```bash
uv run python -m cmd.generate_pir \
  --context tests/fixtures/sample_context_manufacturing.json \
  --no-llm \
  --output pir_output.json
```

### Generate PIR (with Vertex AI)

```bash
export GCP_PROJECT_ID=your-project-id

uv run python -m cmd.generate_pir \
  --context tests/fixtures/sample_context_manufacturing.json \
  --output pir_output.json
```

### Parse Markdown input

```bash
uv run python -m cmd.generate_pir \
  --context strategy_doc.md \
  --output pir_output.json
```

### Validate PIR for SAGE compatibility

```bash
uv run python -m cmd.validate_pir --pir pir_output.json
```

---

## Input: BusinessContext JSON

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
  "supply_chain": {
    "ot_connectivity": true,
    "cloud_providers": ["GCP"]
  }
}
```

Full schema: `schema/business_context.schema.json` (generate with `uv run python -m cmd.generate_schemas`)

---

## Output: PIR JSON (SAGE-compatible)

```json
[
  {
    "pir_id": "PIR-2026-001",
    "intelligence_level": "strategic",
    "description": "製造業×日本 環境のクラウンジュエル（PLM system）を狙う脅威アクターへの耐性強化",
    "rationale": "Likelihood=5, Impact=5 — 業種×地域マッチ: state_sponsored.China, ransomware / OT接続によるラテラルムーブリスクあり",
    "threat_actor_tags": ["apt-china", "espionage", "ip-theft", "ot-targeting", "ransomware"],
    "asset_weight_rules": [
      { "tag": "plm", "criticality_multiplier": 2.5 },
      { "tag": "ot",  "criticality_multiplier": 2.0 }
    ],
    "collection_focus": ["MirrorFace / APT10 の新規TTP観測", "OT/ICS環境を標的とする脆弱性悪用情報"],
    "valid_from": "2026-04-04",
    "valid_until": "2027-04-04",
    "risk_score": { "likelihood": 5, "impact": 5, "composite": 25 }
  }
]
```

Only P1 (composite ≥ 20) and P2 (composite ≥ 12) are output. Lower-priority items are tracked in `collection_plan.md` (Phase 3).

---

## Intelligence Level & Validity

| Level | composite | valid_until | Example |
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

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GCP_PROJECT_ID` | — | GCP project (shared with SAGE) |
| `VERTEX_LOCATION` | `us-central1` | Vertex AI region |
| `BEACON_LLM_SIMPLE` | `gemini-2.5-flash-lite` | Simple task model |
| `BEACON_LLM_MEDIUM` | `gemini-2.5-flash` | Medium task model |
| `BEACON_LLM_COMPLEX` | `gemini-2.5-pro` | Complex reasoning model |

---

## Project Structure

```
BEACON/
├── pyproject.toml             # uv + ruff
├── Makefile                   # check / generate / validate / test / audit
├── CHANGELOG.md
├── src/beacon/
│   ├── config.py
│   ├── ingest/
│   │   ├── schema.py          # BusinessContext Pydantic models
│   │   └── context_parser.py  # JSON / Markdown parser
│   ├── analysis/
│   │   ├── element_extractor.py  # Step 1
│   │   ├── asset_mapper.py       # Step 2
│   │   ├── threat_mapper.py      # Step 3
│   │   └── risk_scorer.py        # Step 4
│   ├── generator/
│   │   ├── pir_builder.py        # Step 5
│   │   └── report_builder.py     # collection_plan.md (Phase 3)
│   └── llm/
│       ├── client.py
│       └── prompts/
│           ├── context_structuring.md
│           ├── pir_generation.md
│           └── threat_tag_completion.md
├── cmd/
│   ├── generate_pir.py
│   ├── validate_pir.py
│   └── generate_schemas.py
├── schema/
│   ├── threat_taxonomy.json
│   ├── asset_tags.json
│   ├── business_context.schema.json  (generated)
│   └── pir_output.schema.json        (generated)
├── tests/
│   ├── fixtures/
│   │   ├── sample_context_manufacturing.json
│   │   └── sample_context_finance.md
│   └── test_*.py              # No SAGE dependency required
└── docs/
    ├── dependencies.md
    ├── sage_integration.md    # SAGE ETL verification procedure (EN)
    └── ja/
        └── sage_integration.md  # SAGE ETL verification procedure (JA)
```

---

## Development

```bash
# Quality gate (lint + test, excludes integration tests)
make check

# Run tests only
make test

# Run integration tests (requires GCP_PROJECT_ID)
make test-integration

# Security audit
make audit

# Generate JSON schemas from Pydantic models
uv run python cmd/generate_schemas.py
```

### Test suite overview

| Test file | What it covers | SAGE required? |
|-----------|---------------|----------------|
| `test_element_extractor.py` | Step 1: element extraction | No |
| `test_threat_mapper.py` | Step 3: threat mapping (dictionary) | No |
| `test_risk_scorer.py` | Step 4: risk scoring | No |
| `test_pir_builder.py` | Step 5: PIR JSON generation | No |
| `test_report_builder.py` | collection_plan.md generation | No |
| `test_sage_compatibility.py` | PIR field contract for SAGE PIRFilter | No |
| `test_context_parser_md.py` | Markdown → BusinessContext (LLM mock) | No |
| `test_llm_client.py` | Vertex AI client (mocked) | No |

`test_sage_compatibility.py` verifies the PIR field contract inline — the SAGE repository is **not required** to run any tests.

---

## Integration with SAGE

```
[Analyst]
    │  Create / update business_context.json
    ▼
[BEACON: generate_pir]
    │  pir_output.json
    ▼
[Analyst review]
    │  Review PIR content, edit if needed
    ▼
[Place at SAGE PIR_FILE_PATH]
    │  cp pir_output.json /config/pir.json
    ▼
[SAGE ETL]
    │  Targets edges + pir_adjusted_criticality updated
    ▼
[SAGE Analysis API]
    │  Choke-point / attack-path queries reflect PIR weights
```

Recommended update frequency: quarterly, or on significant organizational changes (M&A, new projects, OT expansion).

---

## Threat Taxonomy Coverage

`schema/threat_taxonomy.json` (MITRE ATT&CK Groups v15-based):

| Category | Groups |
|----------|--------|
| China (state) | APT10, APT41, MirrorFace, Mustang Panda |
| Russia (state) | APT28, APT29, Sandworm |
| North Korea (state) | Lazarus, Kimsuky, APT38 |
| Iran (state) | APT33, APT34, MuddyWater |
| Ransomware | LockBit, RansomHub, BlackCat, Cl0p |
| Hacktivist | (tag-based, no named groups) |

Industries covered: manufacturing, finance, energy, healthcare, defense, technology, logistics, government, education.
