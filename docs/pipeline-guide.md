# CTI Pipeline Operations Guide

End-to-end workflow: BEACON → TRACE → SAGE.

## Data Flow

```
context.md ──→ BEACON ──→ TRACE ──→ SAGE
  (input)       (PIR)     (collect)   (analyze)
```

---

## Phase 1: BEACON — PIR + Assets

BEACON converts a business context document into Priority Intelligence Requirements (PIR)
and asset bundles for SAGE. It scores threat relevance using industry/geography matching,
optional Gemini LLM enrichment, and SAGE actor-triage IR-boost.

Key commands:

- `beacon pir-generate` — generate PIR + collection plan + recommended sources
- `beacon assets-generate` — generate SAGE-compatible assets.json
- `beacon identity-generate` — generate identity_assets.json
- `beacon accounts-generate` — generate user_accounts.json
- `beacon web` — 5-tab dashboard (http://localhost:8000)

→ Full details: [BEACON docs/usage.md](usage.md)

---

## Phase 2: TRACE — Collection + Validation

TRACE validates BEACON output artifacts and collects external CTI reports from
URLs and PDFs. A PIR-driven L2 relevance gate filters content before STIX 2.1
bundle extraction with LLM-powered IoC indexing.

Key commands:

- `trace validate-all` — validate PIR + assets before collection
- `trace crawl-single` — crawl a single URL or PDF with PIR gate
- `trace crawl-batch` — batch-crawl a sources list from BEACON
- `trace validate-stix` — validate collected STIX bundles
- `trace enrich-bundle` — add PIR taxonomy tags to bundles
- `trace search-iocs` — query the crawl-state IoC index

→ Full details: [TRACE docs/usage.md](https://github.com/sw33t-b1u/trace/blob/main/docs/usage.md)

---

## Phase 3: SAGE — Analysis

SAGE ingests BEACON asset bundles and TRACE STIX bundles into a Spanner Graph,
computes FollowedBy transition weights, applies PIR-based criticality adjustment,
and exposes an Analysis API for attack-path queries and threat summaries.

Key commands:

- `sage init-schema` — initialize Spanner Graph schema (first time only)
- `sage load-assets` — load BEACON asset bundles
- `sage run-etl` — ingest STIX bundles into Spanner Graph
- `sage serve-api` — start the Analysis API (default port 8080)
- `sage visualize-graph` — generate interactive HTML graph
- `sage incident-register` — register IR feedback (Diamond Model)

→ Full details: [SAGE docs/usage.md](https://github.com/sw33t-b1u/sage/blob/main/docs/usage.md)

---

## Feedback Loop

On subsequent BEACON runs, `beacon pir-generate --use-sage` pulls SAGE observation
data (incident history, actor counts) into the actor-triage Intent score (`ir_observed`),
improving PIR accuracy as the system accumulates operational history.

→ IR feedback loop formulas: [SAGE ir-feedback-flow.md](https://github.com/sw33t-b1u/sage/blob/main/docs/ir-feedback-flow.md)

---

## Environment Variables (Quick Reference)

### BEACON

| Variable | Default | Purpose |
|---|---|---|
| `GCP_PROJECT_ID` | (none) | Vertex AI project for LLM calls |
| `BEACON_LLM_SIMPLE` | `gemini-2.5-flash-lite` | Model for simple extraction tasks |
| `BEACON_LLM_MEDIUM` | `gemini-2.5-flash` | Model for medium-complexity analysis |
| `BEACON_LLM_COMPLEX` | `gemini-2.5-pro` | Model for complex reasoning (PIR generation) |
| `SAGE_API_URL` | (none) | SAGE API base URL (enables `--use-sage`) |
| `BEACON_IR_LOOKBACK_DAYS` | `365` | IR-boost lookback window in days |
| `BEACON_STORAGE` | `local` | Storage backend: `local` or `gcs` |
| `BEACON_STORAGE_BASE_DIR` | `output/` | Base directory for `local` backend |
| `BEACON_STORAGE_BUCKET` | (none) | GCS bucket name (required for `gcs` backend) |
| `BEACON_STORAGE_PREFIX` | (empty) | Key prefix within the GCS bucket |
| `TRACE_ROOT_PATH` | (none) | Absolute path to the TRACE repo root (enables Collection tab) |

### TRACE

| Variable | Default | Purpose |
|---|---|---|
| `GCP_PROJECT_ID` | (none) | Vertex AI project for LLM calls |
| `TRACE_LLM_SIMPLE` | `gemini-2.5-flash-lite` | Model for relevance scoring |
| `TRACE_LLM_MEDIUM` | `gemini-2.5-flash` | Model for STIX extraction |
| `TRACE_RELEVANCE_THRESHOLD` | `0.5` | L2 PIR relevance gate threshold (0.0–1.0) |
| `TRACE_CRAWL_CONCURRENCY` | `4` | Parallel crawl workers |
| `TRACE_FEED_MAX_ENTRIES` | `50` | Max RSS feed entries per source |
| `TRACE_STORAGE` | `local` | Storage backend: `local` or `gcs` |
| `TRACE_STORAGE_BASE_DIR` | `output/` | Base directory for `local` backend |
| `TRACE_STORAGE_BUCKET` | (none) | GCS bucket name (required for `gcs` backend) |
| `TRACE_STORAGE_PREFIX` | (empty) | Key prefix within the GCS bucket |

### SAGE

| Variable | Default | Purpose |
|---|---|---|
| `GCP_PROJECT_ID` | (none) | Spanner project |
| `SPANNER_INSTANCE` | (required) | Spanner instance ID |
| `SPANNER_DB` | (required) | Spanner database ID |
| `SAGE_API_AUTH_TOKEN` | (none) | Bearer token for API auth; POST returns 503 when unset |
| `PIR_FILE_PATH` | `/config/pir.json` | Path to BEACON pir_output.json (used by ETL for relevance filtering) |
| `SAGE_STORAGE` | `local` | Storage backend: `local` or `gcs` |
| `SAGE_STORAGE_BASE_DIR` | `output` | Base directory for local storage (shared with TRACE/BEACON) |
| `SAGE_STORAGE_BUCKET` | (none) | GCS bucket name (required when `SAGE_STORAGE=gcs`) |
| `SAGE_STORAGE_PREFIX` | (none) | GCS object key prefix (optional) |

---

## Command Cheat Sheet

```bash
# --- Phase 1: BEACON ---
uv run beacon pir-generate --context input/context.md
uv run beacon assets-generate --context input/context.md
uv run beacon identity-generate --context input/context.md
uv run beacon accounts-generate --context input/context.md
uv run beacon web

# --- Phase 2: TRACE ---
uv run trace validate-all --pir ../BEACON/output/pir_output.json --it-assets ../BEACON/output/assets.json
uv run trace crawl-single --input <URL> --pir ../BEACON/output/pir_output.json
uv run trace crawl-batch --sources input/sources.yaml --pir ../BEACON/output/pir_output.json
uv run trace validate-stix --bundle output/stix/*.json
uv run trace enrich-bundle --input output/stix/bundle.json --output output/stix/bundle_enriched.json
uv run trace search-iocs --ioc <indicator>

# --- Phase 3: SAGE ---
uv run sage init-schema
uv run sage load-assets
uv run sage run-etl
uv run sage serve-api --port 8080
uv run sage visualize-graph
uv run sage incident-register
```
