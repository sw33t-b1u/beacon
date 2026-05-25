# CTI Pipeline Operations Guide

End-to-end workflow for BEACON, TRACE, and SAGE — from business context
to actionable threat intelligence.

```
context.md ──→ BEACON ──→ TRACE ──→ SAGE
  (input)       (PIR)     (collect)   (analyze)
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python ≥ 3.12 | All three projects target 3.12+ |
| `uv` | Package manager; run `uv sync` in each repo |
| GCP Project (Vertex AI) | `GCP_PROJECT_ID` env var; used by BEACON + TRACE LLM calls |
| GCP Spanner instance | SAGE storage backend; set `SPANNER_INSTANCE` + `SPANNER_DB` |
| `beacon` / `trace` / `sage` CLI | Installed via `uv sync` in each repo (see `[project.scripts]` in pyproject.toml) |

---

## Phase 1: BEACON — PIR Development + Collection Strategy

### 1.1 Prepare the business context document

Create `input/context.md` following the template at `docs/context_template.md`
(Japanese: `docs/context_template.ja.md`). The document should cover:

| Section | Impact on PIR Generation |
|---|---|
| Organization Overview (industry, geography, size) | Industry-specific threat matching; `geopolitical_exposure` trigger |
| Strategic Objectives (M&A, IPO, partnerships) | `m_and_a`, `ipo_or_listing` triggers |
| Projects (AI/ML adoption) | `ai_adoption_exposure` trigger |
| IT Assets (servers, networks, cloud) | Asset bundle for SAGE attack-path analysis |
| Business Continuity (BCP, DR test cadence) | `ransomware_resilience_gap` trigger |
| Identity Management (MFA %, PIM/PAM) | `identity_credential_exposure` trigger |
| Regulatory Requirements (e.g. FISC, PCI-DSS) | `regulatory_change` trigger |

### 1.2 Generate PIR + collection plan + recommended sources

```bash
cd BEACON/

uv run beacon pir-generate \
  --context input/context.md \
  --output-dir output/
```

Three artifacts are produced and a review web UI auto-launches:

| Output | Purpose |
|---|---|
| `output/pir_output.json` | PIR document (CU-GIR decimal IDs, schema_version 1.0.0, wrapped envelope) |
| `output/collection_plan.md` | Per-PIR collection guidance: frequency, responsible role, recommended actions |
| `output/sources_candidate.yaml` | Recommended CTI sources with tier / region / industry / ATT&CK Group ID annotations |

The web UI (`http://localhost:<port>/`) presents all generated artifacts
for interactive review. Suppress with `--no-web` if running headless.

**Key options:**

| Flag | Effect |
|---|---|
| `--use-sage` | Pull SAGE observation counts into risk scoring (requires `SAGE_API_URL`) |
| `--no-sage` | Skip actor-triage IR-boost SAGE call |
| `--save-context path` | Write the parsed BusinessContext as JSON for inspection |

### 1.3 Generate asset bundles (for SAGE ingestion)

```bash
uv run beacon assets-generate --context input/context.md
uv run beacon identity-generate --context input/context.md
uv run beacon accounts-generate --context input/context.md
```

Produces `output/assets.json`, `output/identity_assets.json`, and
`output/user_accounts.json`.

---

## Phase 2: TRACE — Threat Collection + Validation

### 2.1 Validate BEACON outputs

```bash
cd TRACE/

uv run trace validate-all \
  --pir ../BEACON/output/pir_output.json \
  --it-assets ../BEACON/output/assets.json
```

Runs the PIR and asset validators and emits a Markdown report.
Fix any findings before proceeding.

Identity and account validation use separate commands:

```bash
uv run trace validate-identity --identity-assets ../BEACON/output/identity_assets.json \
                               --it-assets ../BEACON/output/assets.json
uv run trace validate-accounts --user-accounts ../BEACON/output/user_accounts.json \
                               --it-assets ../BEACON/output/assets.json
```

### 2.2 Collect threat reports (PIR-driven)

**Single URL or PDF:**

```bash
uv run trace crawl-single \
  --input https://www.jpcert.or.jp/at/2025/at250001.html \
  --pir ../BEACON/output/pir_output.json
```

The L2 PIR relevance gate automatically scores the content against your
PIRs. Articles below the threshold are skipped; relevant articles produce
a STIX 2.1 bundle with LLM-extracted IoCs.

**Batch collection from recommended sources:**

```bash
cp ../BEACON/output/sources_candidate.yaml input/sources.yaml

uv run trace crawl-batch \
  --sources input/sources.yaml \
  --pir ../BEACON/output/pir_output.json \
  --output-dir output/stix/
```

Each source URL listed in `sources_candidate.yaml` is crawled; only
content passing the PIR relevance gate is converted to STIX bundles.

### 2.3 Validate collected STIX bundles

```bash
uv run trace validate-stix --bundle output/stix/*.json
```

### 2.4 Enrich bundles with PIR tags (optional)

```bash
uv run trace enrich-bundle \
  --input output/stix/bundle_xxx.json \
  --output output/stix/bundle_xxx_enriched.json
```

Adds taxonomy tags to STIX objects for downstream filtering in SAGE.

### 2.5 Search extracted IoCs

```bash
uv run trace search-iocs --ioc 203.0.113.42
```

Queries the crawl-state IoC index for a specific indicator value.

---

## Phase 3: SAGE — Threat Analysis + Risk Assessment

### 3.1 Initialize the Spanner Graph (first time only)

```bash
cd SAGE/

uv run sage init-schema
```

### 3.2 Load BEACON asset data

```bash
uv run sage load-assets           --input ../BEACON/output/assets.json
uv run sage load-identity-assets  --input ../BEACON/output/identity_assets.json
uv run sage load-user-accounts    --input ../BEACON/output/user_accounts.json
```

### 3.3 Ingest STIX bundles (ETL)

```bash
export PIR_FILE_PATH=../BEACON/output/pir_output.json

uv run sage run-etl --input ../TRACE/output/stix/bundle.json
```

The `PIR_FILE_PATH` env var points to the BEACON PIR output (required for
relevance filtering during ingestion). The `--input` flag accepts
a single STIX bundle file. Repeat for each bundle, or use a shell loop:

```bash
for f in ../TRACE/output/stix/*.json; do uv run sage run-etl --input "$f"; done
```

The ETL pipeline parses STIX 2.1 bundles, maps objects to Spanner Graph
nodes and edges, computes `FollowedBy` transition weights from kill-chain
phase ordering, and applies PIR-based asset criticality adjustment.

### 3.4 Start the Analysis API

```bash
uv run sage serve-api --port 8080
```

### 3.5 Query threat intelligence

| Endpoint | Method | Purpose |
|---|---|---|
| `/threat-summary?asset=<id>` | GET | Aggregated per-asset view: actors, attack paths, choke points, vulnerabilities, incidents |
| `/actor-ttps?actor_id=<id>&since=YYYY-MM-DD&until=YYYY-MM-DD` | GET | Per-actor TTP list with time-range filter |
| `/attack-paths?asset_id=<id>&limit=N` | GET | Multi-hop attack path search (actor → asset) |
| `/choke-points` | GET | Defense priority — graph-wide choke-point computation |
| `/asset-exposure?since=YYYY-MM-DD` | GET | Externally-exposed assets and reachable TTP counts (time-windowed) |
| `/similar-incidents?incident_id=<id>` | GET | Hybrid-score similar-incident search (TTP Jaccard + transition coverage) |
| `/api/incidents` | POST | Register an incident directly (Diamond Model) |
| `/api/incidents?since=YYYY-MM-DD` | GET | Retrieve registered incidents |
| `/api/annotate` | POST | Write an analyst annotation on an actor |

**Example — threat trends for the past 6 months:**

```bash
# Actor TTPs since 6 months ago
curl "http://localhost:8080/actor-ttps?actor_id=intrusion-set--apt-XX&since=2025-01-01"

# Per-asset threat summary
curl "http://localhost:8080/threat-summary?asset=core-banking-001"

# Attack paths to a critical asset
curl "http://localhost:8080/attack-paths?asset_id=core-banking-001&limit=10"
```

### 3.6 Visualize the attack graph

```bash
uv run sage visualize-graph
```

Generates an interactive HTML visualization of the Spanner Graph
(nodes + edges rendered via pyvis).

### 3.7 Register IR feedback (optional)

Record past incidents for the IR-boost feedback loop:

```bash
uv run sage incident-register
```

Interactive Diamond Model 4-quadrant prompt (adversary / capability /
infrastructure / victim) with kill-chain phase and IoC fields.

---

## Feedback Loop

```
                 ┌──────────────────────────────────────────┐
                 │                                          ▼
BEACON           TRACE              SAGE               BEACON (next run)
pir-generate ──→ crawl-batch ──→  run-etl ──→         pir-generate
  PIR             (PIR gate)      Spanner Graph          --use-sage
  collection      STIX bundles    /threat-summary         │
  sources.yaml                    /actor-ttps             IR boost
                                  incident-register ──→  reflected in
                                                         Likelihood
```

On subsequent runs, `beacon pir-generate --use-sage` pulls observation
data from SAGE into the actor-triage Likelihood score
(`ir_observed_capability` + `ir_observed_opportunity`), improving PIR
accuracy as the system accumulates operational history.

---

## Environment Variables

### BEACON

| Variable | Default | Purpose |
|---|---|---|
| `GCP_PROJECT_ID` | (none) | Vertex AI project for LLM calls |
| `BEACON_LLM_SIMPLE` | `gemini-2.5-flash-lite` | Model for simple extraction tasks |
| `BEACON_LLM_MEDIUM` | `gemini-2.5-flash` | Model for medium-complexity analysis |
| `BEACON_LLM_COMPLEX` | `gemini-2.5-pro` | Model for complex reasoning (PIR generation) |
| `SAGE_API_URL` | (none) | SAGE API base URL (enables `--use-sage`) |
| `BEACON_IR_LOOKBACK_DAYS` | `365` | IR-boost lookback window in days |

### TRACE

| Variable | Default | Purpose |
|---|---|---|
| `GCP_PROJECT_ID` | (none) | Vertex AI project for LLM calls |
| `TRACE_LLM_SIMPLE` | `gemini-2.5-flash-lite` | Model for relevance scoring |
| `TRACE_LLM_MEDIUM` | `gemini-2.5-flash` | Model for STIX extraction |
| `TRACE_RELEVANCE_THRESHOLD` | `0.5` | L2 PIR relevance gate threshold (0.0–1.0) |
| `TRACE_CRAWL_CONCURRENCY` | `4` | Parallel crawl workers |
| `TRACE_FEED_MAX_ENTRIES` | `50` | Max RSS feed entries per source |

### SAGE

| Variable | Default | Purpose |
|---|---|---|
| `GCP_PROJECT_ID` | (none) | Spanner project |
| `SPANNER_INSTANCE` | (required) | Spanner instance ID |
| `SPANNER_DB` | (required) | Spanner database ID |
| `SAGE_API_AUTH_TOKEN` | (none) | Bearer token for API auth; POST returns 503 when unset |
| `PIR_FILE_PATH` | `/config/pir.json` | Path to BEACON pir_output.json (used by ETL for relevance filtering) |

---

## Quick Reference — Command Cheat Sheet

```bash
# --- Phase 1: BEACON ---
uv run beacon pir-generate --context input/context.md
uv run beacon assets-generate --context input/context.md
uv run beacon identity-generate --context input/context.md
uv run beacon accounts-generate --context input/context.md
uv run beacon web                                    # review UI only

# --- Phase 2: TRACE ---
uv run trace validate-all --pir ../BEACON/output/pir_output.json --it-assets ../BEACON/output/assets.json
uv run trace crawl-single --input <URL> --pir ../BEACON/output/pir_output.json
uv run trace crawl-batch --sources input/sources.yaml --pir ../BEACON/output/pir_output.json
uv run trace validate-stix --bundle output/stix/*.json
uv run trace enrich-bundle --input output/stix/bundle.json --output output/stix/bundle_enriched.json
uv run trace search-iocs --ioc <indicator>

# --- Phase 3: SAGE ---
uv run sage init-schema
uv run sage load-assets --input ../BEACON/output/assets.json
uv run sage run-etl --input ../TRACE/output/stix/bundle.json
uv run sage serve-api --port 8080
uv run sage query-attack-paths --asset-id <id>
uv run sage visualize-graph
uv run sage incident-register
```
