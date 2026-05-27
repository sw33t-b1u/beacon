# BEACON

**Business Environment Assessment for CTI Organizational Needs**

Converts organizational business context (JSON or Markdown strategy documents) into [SAGE](https://github.com/sw33t-b1u/sage)-compatible **Priority Intelligence Requirements (PIR) JSON** using a dictionary-based pipeline augmented by Google Gen AI (Gemini).

[日本語版 README はこちら](README.ja.md)

> PIRs are the "information requirements that security needs to protect the business." BEACON bridges the gap between business strategy and CTI prioritization.

## Overview

BEACON provides four output pipelines, all driven from the same context document:

```
  input/context.md  (or .json)
         │
         ├─── cmd/generate_pir.py ──────────────────────────────────────────┐
         │                                                                   │
         │    ┌──────────────────────┐                                       │
         │    │ Step 1: Element Ext. │  objectives, crown jewels, assets     │
         │    │ Step 2: Asset Map    │  → SAGE tags (plm, ot, erp …)        │
         │    │ Step 3: Threat Map   │  industry × geography → actor tags    │
         │    │ Step 4: Risk Score   │  Likelihood × Impact (1–5)            │
         │    │ Step 5: PIR Build    │  SAGE-compatible PIR JSON             │
         │    └──────────────────────┘                                       │
         │                        output/pir_output.json ────────────────────┘
         │                                  │                        │
         │                                  ▼                        ▼
         │                           SAGE ETL             pir_adjusted_criticality
         │
         ├─── cmd/generate_assets.py ─── output/assets.json ─── SAGE load_assets
         │        CriticalAsset → network segments,
         │        asset tags, connections, criticality
         │
         ├─── cmd/generate_identity_assets.py ── output/identity_assets.json
         │        Identity + has_access edges            │
         │        (+ Initiative C Phase 2 flags:         ▼
         │         is_high_value_impersonation_target,   TRACE validate_identity_assets
         │         impersonation_risk_factors)           │
         │                                                ▼
         │                                       SAGE load_identity_assets
         │
         └─── cmd/generate_user_accounts.py ──── output/user_accounts.json
                  UserAccount + account_on_asset edges  │
                                                         ▼
                                              TRACE validate_user_accounts
                                                         │
                                                         ▼
                                              SAGE load_user_accounts
```

> **CTI report ingestion (PDF / URL → STIX 2.1) has moved to the sibling
> project [TRACE](../TRACE/) as of BEACON 0.9.0.** Use `TRACE/cmd/crawl_single.py`
> instead of the removed `BEACON/cmd/stix_from_report.py`.

**Modes:**

| Mode | Input | LLM | Use case |
|------|-------|-----|----------|
| `--no-llm` | JSON only | None | Air-gapped / cost-constrained |
| Default | JSON or Markdown | Gemini (Vertex AI) | Full quality PIR + assets |

## Documentation

| Document | Description |
|----------|-------------|
| [docs/setup.md](docs/setup.md) | Prerequisites, installation, environment variables, GCP authentication |
| [schema/context_template.md](schema/context_template.md) | Template for `input/context.md` — the Markdown strategy document used as pipeline input |
| [docs/data-model.md](docs/data-model.md) | BusinessContext schema, PIR output format, `identity_assets.json` / `user_accounts.json` schemas, intelligence levels, threat taxonomy |
| [docs/operations.md](docs/operations.md) | Day-to-day operations, MISP cache refresh, SAGE integration and ETL verification |
| [docs/dependencies.md](docs/dependencies.md) | Dependency rationale and license information |
| [docs/pipeline-guide.md](docs/pipeline-guide.md) | End-to-end CTI pipeline workflow: BEACON → TRACE → SAGE ([ja](docs/pipeline-guide.ja.md)) |

## Storage Backend (Initiative I)

BEACON 1.1.0 introduces a **StorageBackend** abstraction for artifact persistence. All
generated artifacts (`pir_output.json`, `assets.json`, STIX bundles, etc.) are saved
through a pluggable backend instead of writing directly to `output/`.

| Backend | Description | Activation |
|---------|-------------|------------|
| `local` (default) | Writes to a local directory | `BEACON_STORAGE=local` |
| `gcs` | Writes to Google Cloud Storage | `BEACON_STORAGE=gcs` |

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `BEACON_STORAGE` | `local` | Storage backend: `local` or `gcs` |
| `BEACON_STORAGE_BASE_DIR` | `output/` | Base directory for `local` backend |
| `BEACON_GCS_BUCKET` | — | GCS bucket name (required for `gcs` backend) |
| `BEACON_GCS_PREFIX` | (empty) | Key prefix within the GCS bucket |

GCS support requires `google-cloud-storage` (optional install):

```bash
uv sync --extra gcs
```

Artifact filenames follow the pattern `<type>_<YYYYMMDDHHmm>.json`
(e.g., `pir_202506011430.json`). Categories: `pir`, `assets`, `stix`, `plans`, `crawl_state`.

## Web Dashboard (Initiative I)

The web UI (`uv run beacon web`, default `http://localhost:8000`) has been unified into a
**5-tab dashboard**:

| Tab | Purpose |
|-----|---------|
| **Dashboard** | Pipeline summary: PIR count, collection status, choke-points |
| **PIR** | Generate PIR, review output, StorageBackend auto-load of previous runs |
| **Collection** | Run TRACE `crawl-single` / `crawl-batch` via subprocess |
| **Threats** | SAGE API proxy: actor search, TTP lookup, threat-summary |
| **Settings** | Configure storage mode, SAGE URL, TRACE path; persisted to `.beacon_settings.json` |

Settings follow the priority chain: **env vars > `.beacon_settings.json` > defaults**.

> **Deprecation (BEACON 1.1.0):** `cmd/submit_for_review.py` (GHE Issue creation) is
> deprecated and will be removed in a future release. The **Settings tab** in the web
> dashboard replaces the GHE approval workflow with a built-in web approval flow. Set
> `TRACE_ROOT_PATH` to point the Collection tab at your TRACE installation.

## Quick Start

```bash
cd BEACON
uv sync --extra dev
make setup             # Install Git hooks
cp .env.example .env   # Fill in GCP_PROJECT_ID and other variables as needed
```

See [docs/setup.md](docs/setup.md) for the full setup procedure.

## Project Structure

See [docs/structure.md](docs/structure.md) for the full directory layout and design criteria.

## Development

```bash
make setup     # Install Git hooks (run once after cloning)
make check     # lint + test + audit (full quality gate)
make vet       # ruff check
make lint      # ruff format --check
make format    # ruff format + fix
make test      # pytest (unit tests)
make audit     # pip-audit
```

## PIR Methodology References

BEACON's PIR generation follows published CTI methodology:

- [FIRST CTI-SIG — Priority Intelligence Requirements curriculum](https://www.first.org/global/sigs/cti/curriculum/pir)
- [SANS — Bridging Gaps in CTI: A Practical Guide to Threat-Informed Security PIRs](https://www.sans.org/blog/bridging-gaps-cti-practical-guide-threat-informed-security-pirs)

Key guidance applied: one PIR = one decision point; "less is more" (≤5 per run); cascade Strategic PIR → Operational TAP → Tactical PTTP. See `src/beacon/analysis/pir_clusterer.py`.

## License

Apache-2.0 — see [LICENSE](LICENSE)
