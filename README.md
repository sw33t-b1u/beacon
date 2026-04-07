# BEACON

**Business Environment Assessment for CTI Organizational Needs**

Converts organizational business context (JSON or Markdown strategy documents) into [SAGE](../SAGE)-compatible **Priority Intelligence Requirements (PIR) JSON** using a dictionary-based pipeline augmented by Google Gen AI (Gemini).

[日本語版 README はこちら](README.ja.md)

> PIRs are the "information requirements that security needs to protect the business." BEACON bridges the gap between business strategy and CTI prioritization.

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
| Default | JSON or Markdown | Google Gen AI (Gemini) | Full quality |

## Documentation

| Document | Description |
|----------|-------------|
| [docs/setup.md](docs/setup.md) | Prerequisites, installation, environment variables, GCP authentication |
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

```
BEACON/
├── pyproject.toml
├── Makefile
├── .env.example
├── src/beacon/
│   ├── config.py
│   ├── ingest/{schema,context_parser}.py
│   ├── analysis/{element_extractor,asset_mapper,threat_mapper,risk_scorer}.py
│   ├── generator/{pir_builder,report_builder}.py
│   ├── llm/{client,prompts/}
│   ├── review/github.py
│   ├── sage/client.py
│   └── web/{app,session,templates/}
├── cmd/
│   ├── generate_pir.py
│   ├── validate_pir.py
│   ├── generate_schemas.py
│   ├── update_taxonomy.py
│   ├── submit_for_review.py
│   └── web_app.py
├── schema/
│   ├── threat_taxonomy.json
│   ├── asset_tags.json
│   ├── content_ja.json
│   └── trigger_keywords.json
└── tests/
    ├── fixtures/
    └── test_*.py
```

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
