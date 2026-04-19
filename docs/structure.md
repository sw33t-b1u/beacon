# BEACON — Project Directory Structure

This document describes the top-level layout of the BEACON repository.

```
BEACON/
├── src/beacon/                  # Core Python package
│   ├── config.py                # Environment-based configuration (Config dataclass)
│   ├── ingest/
│   │   ├── schema.py            # BusinessContext / CriticalAsset Pydantic models
│   │   ├── context_parser.py    # JSON/Markdown → BusinessContext conversion
│   │   ├── report_reader.py     # PDF / URL / text → Markdown (via markitdown)
│   │   └── stix_extractor.py    # LLM-driven STIX 2.1 object extraction
│   ├── analysis/
│   │   ├── element_extractor.py # Step 1: business element extraction
│   │   ├── asset_mapper.py      # Step 2: element → SAGE asset tags
│   │   ├── assets_generator.py  # CriticalAsset → SAGE-compatible assets.json
│   │   ├── threat_mapper.py     # Step 3: industry × geography → threat actor tags
│   │   └── risk_scorer.py       # Step 4: Likelihood × Impact scoring
│   ├── generator/
│   │   ├── pir_builder.py       # Step 5: SAGE-compatible PIR JSON generation
│   │   └── report_builder.py    # collection_plan.md generation (P3/P4 items)
│   ├── llm/
│   │   ├── client.py            # Vertex AI Gemini client (google-genai SDK)
│   │   └── prompts/             # Markdown prompt templates
│   │       ├── context_structuring.md    # context.md → BusinessContext JSON
│   │       ├── pir_generation.md         # PIR text augmentation
│   │       └── stix_extraction.md        # CTI report → STIX 2.1 objects
│   ├── review/
│   │   └── github.py            # GHE/GitHub Issue creation for PIR review
│   ├── sage/
│   │   └── client.py            # SAGE Analysis API client
│   └── web/
│       ├── app.py               # FastAPI routes (GET /, POST /generate, /review)
│       ├── session.py           # Session management ($TMPDIR/beacon_session_*.json)
│       └── templates/           # Jinja2 HTML templates (base, index, review)
│
├── cmd/                         # CLI entry points (one script per command)
│   ├── generate_pir.py          # Main PIR pipeline (context.md → pir_output.json)
│   ├── generate_assets.py       # CriticalAsset → SAGE assets.json
│   ├── stix_from_report.py      # PDF / URL → STIX 2.1 bundle
│   ├── validate_pir.py          # PIR JSON SAGE compatibility validation
│   ├── generate_schemas.py      # Generate JSONSchema from Pydantic models
│   ├── update_taxonomy.py       # Sync threat taxonomy from MITRE ATT&CK STIX
│   ├── submit_for_review.py     # Create GHE Issues for analyst sign-off
│   └── web_app.py               # Launch Web UI (uvicorn)
│
├── schema/                      # Dictionary and schema files
│   ├── threat_taxonomy.json     # Industry × geography × trigger → threat actor tags
│   ├── asset_tags.json          # Asset type → SAGE tag mapping (with multipliers)
│   ├── content_ja.json          # Japanese content dictionary
│   ├── trigger_keywords.json    # Business trigger keyword patterns
│   ├── business_context.schema.json  # JSONSchema for BusinessContext validation
│   └── pir_output.schema.json        # JSONSchema for PIR output validation
│
├── tests/
│   ├── fixtures/                # Sample JSON / Markdown inputs for unit tests
│   └── test_*.py                # pytest test files
│
├── docs/                        # English documentation (authoritative)
│   ├── setup.md                 # Prerequisites, installation, environment variables
│   ├── context_template.md      # Template for input/context.md
│   ├── data-model.md            # BusinessContext schema, PIR format, LLM integration
│   ├── dependencies.md          # Third-party dependency rationale and licenses
│   ├── sage_integration.md      # PIR deployment to SAGE and ETL verification
│   ├── structure.md             # This file — directory layout reference
│   └── *.ja.md                  # Japanese translations alongside each English doc
│
├── .githooks/                   # Git hooks (install with: make setup)
│   ├── pre-commit               # Runs make vet lint before every commit
│   └── pre-push                 # Runs make check before every push
│
├── high-level-design.md         # Authoritative system design document
├── CHANGELOG.md                 # Version history
├── Makefile                     # Quality gate targets (check, vet, lint, test, audit, setup)
├── pyproject.toml               # Python project config (uv + ruff)
├── uv.lock                      # Locked dependency versions
└── .env.example                 # Template for environment variable configuration
```

## Design criteria

- **`src/beacon/`** contains all reusable library code. Each sub-package has a single responsibility.
- **`cmd/`** contains thin CLI scripts that parse arguments and delegate to `src/beacon/` modules. No business logic lives here.
- **`schema/`** holds the dictionary files and JSONSchemas that drive the pipeline. These are data, not code.
- **`docs/`** holds user-facing documentation. English files use the base name (e.g. `setup.md`); Japanese translations are siblings with the `.ja.md` suffix (e.g. `setup.ja.md`).
- **`high-level-design.md`** must be updated before any architectural change is implemented (Rule 27).
- **`input/`** and **`output/`** are runtime directories gitignored by default — they contain sensitive operational data and must not be committed.
