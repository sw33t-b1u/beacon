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
         ├─── beacon pir-generate ──────────────────────────────────────────┐
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
         ├─── beacon assets-generate ─── output/assets.json ─── SAGE load_assets
         │        CriticalAsset → network segments,
         │        asset tags, connections, criticality
         │
         ├─── beacon identity-generate ── output/identity_assets.json
         │        Identity + has_access edges            │
         │        (+ Initiative C Phase 2 flags:         ▼
         │         is_high_value_impersonation_target,   TRACE validate_identity_assets
         │         impersonation_risk_factors)           │
         │                                                ▼
         │                                       SAGE load_identity_assets
         │
         └─── beacon accounts-generate ──── output/user_accounts.json
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
| [docs/setup.md](docs/setup.md) | Clone, install, configure, test, first run |
| [docs/deploy.md](docs/deploy.md) | Cloud Run deployment |
| [docs/usage.md](docs/usage.md) | Web dashboard, CLI, workflows, operations |
| [docs/pipeline-guide.md](docs/pipeline-guide.md) | End-to-end CTI pipeline (BEACON → TRACE → SAGE) |
| [docs/data-model.md](docs/data-model.md) | PIR output schema, score breakdown, actor triage |
| [docs/structure.md](docs/structure.md) | Project directory layout |
| [docs/dependencies.md](docs/dependencies.md) | Dependency rationale and licenses |
| [docs/api-stability.md](docs/api-stability.md) | API stability policy and BC guarantees |
| [docs/citations.md](docs/citations.md) | External citations and license inventory |
| [schema/context_template.md](schema/context_template.md) | Business context input template |
| [schema/triggers.md](schema/triggers.md) | Business trigger definitions |

Cross-project:
- [SAGE ir-feedback-flow.md](https://github.com/sw33t-b1u/sage/blob/main/docs/ir-feedback-flow.md) — IR feedback loop and scoring formulas

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
