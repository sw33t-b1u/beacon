# BEACON

**Business Environment Assessment for CTI Organizational Needs**

Converts organizational business context (JSON or Markdown strategy documents) into [SAGE](https://github.com/sw33t-b1u/sage)-compatible **Priority Intelligence Requirements (PIR) JSON** using a dictionary-based pipeline augmented by Google Gen AI (Gemini).

[日本語版 README はこちら](README.ja.md)

> PIRs are the "information requirements that security needs to protect the business." BEACON bridges the gap between business strategy and CTI prioritization.

## Overview

BEACON provides three output pipelines, all driven from the same context document:

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
         └─── cmd/generate_assets.py ─── output/assets.json ─── SAGE load_assets
                  CriticalAsset → network segments,
                  asset tags, connections, criticality


  PDF / web article
         │
         └─── cmd/stix_from_report.py ── output/stix_bundle.json ─── SAGE ETL
                  markitdown → clean Markdown → Gemini → STIX 2.1
                  (intrusion-set, attack-pattern, malware, vulnerability …)
```

**Modes:**

| Mode | Input | LLM | Use case |
|------|-------|-----|----------|
| `--no-llm` | JSON only | None | Air-gapped / cost-constrained |
| Default | JSON or Markdown | Gemini (Vertex AI) | Full quality PIR + assets |
| `stix_from_report` | PDF or URL | Gemini (Vertex AI) | CTI report → STIX bundle |

## Documentation

| Document | Description |
|----------|-------------|
| [docs/setup.md](docs/setup.md) | Prerequisites, installation, environment variables, GCP authentication |
| [docs/context_template.md](docs/context_template.md) | Template for `input/context.md` — the Markdown strategy document used as pipeline input |
| [docs/data-model.md](docs/data-model.md) | BusinessContext schema, PIR output format, intelligence levels, threat taxonomy |
| [docs/sage_integration.md](docs/sage_integration.md) | PIR deployment to SAGE and ETL verification procedure |
| [docs/dependencies.md](docs/dependencies.md) | Dependency rationale and license information |

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

## License

Apache-2.0 — see [LICENSE](LICENSE)
