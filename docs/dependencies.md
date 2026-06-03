# BEACON Dependencies

## Runtime Dependencies

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| `pydantic` | `>=2.0` | BusinessContext / PIR input–output schema validation; JSONSchema auto-generation via `model_json_schema()` | MIT |
| `google-genai` | `>=1.0` | Google Gen AI SDK for Vertex AI Gemini calls — used by LLM-mode markdown context parsing (`src/beacon/llm/client.py`) and required for STIX/user-account extraction. | Apache-2.0 |
| `structlog` | `>=24.4.0` | Structured logging (aligned with SAGE) | Apache-2.0 / MIT |
| `httpx` | `>=0.27.0` | HTTP client for MITRE CTI STIX bundle fetch (`cmd/update_taxonomy.py`) and SAGE Analysis API polling (`src/beacon/sage/client.py`) | BSD-3-Clause |
| `fastapi` | `>=0.111.0` | Web UI framework — declarative routing, automatic OpenAPI docs, Jinja2 template integration | MIT |
| `uvicorn[standard]` | `>=0.30.0` | ASGI server for FastAPI (`cmd/web_app.py`); `[standard]` extras include WebSocket and HTTP/2 support | BSD-3-Clause |
| `python-multipart` | `>=0.0.27` | Multipart form-data parsing for file uploads in FastAPI (`POST /generate`). Pinned to `>=0.0.27` for CVE-2026-42561 fix. | Apache-2.0 |
| `jinja2` | `>=3.1.0` | HTML template rendering for the Web UI (`src/beacon/web/templates/`) | BSD-3-Clause |
| `cryptography` | `>=46.0.7` | Transitive dependency of `google-genai` / `uvicorn`. Pinned to `>=46.0.7` to resolve CVE-2026-39892 in 46.0.6. No direct usage in BEACON code. | Apache-2.0 / BSD |
| `python-dotenv` | `>=1.0` | Loads `.env` file into `os.environ` at startup, keeping secrets out of source code | BSD-3-Clause |
| `click` | `>=8.1.0` | Backs the unified `beacon` CLI entry point (`src/beacon/cli/`) introduced in Initiative H Phase 6. Click's `Group` + `command` decorators give us composable subcommands, automatic `--help`, and a testable `CliRunner`. | BSD-3-Clause |
| `google-cloud-storage` | `>=2.18.0` | GCS backend for StorageBackend (`src/beacon/storage/gcs.py`). Required for `BEACON_STORAGE=gcs`; installed unconditionally as a main dep since 2.1.2. | Apache-2.0 |

## Optional Dependencies

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| `pymisp` | `>=2.4` | Optional live MISP Galaxy fetch in `src/beacon/ingest/misp_client.py`. Install with `pip install 'beacon[misp]'`. Not required for offline / cache-based operation. | BSD-2-Clause |

## Development Dependencies

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| `ruff` | `>=0.6.0` | Lint + format (aligned with SAGE) | MIT |
| `pytest` | `>=9.0.3` | Test framework | MIT |
| `pytest-cov` | `>=5.0.0` | Coverage measurement | MIT |
| `pip-audit` | `>=2.7.0` | Known-vulnerability scanning (`make audit`, included in `make check`) | Apache-2.0 |

## Dependency Selection Rationale

- **pydantic**: Type-safe input validation was required from Phase 1. v2 is fast and supports `model_json_schema()` for automatic JSONSchema generation.
- **google-genai**: Google Gen AI SDK (successor to `google-cloud-aiplatform` vertexai sub-package). Uses ADC authentication within the same GCP project as SAGE, eliminating API key management. Migrated from `vertexai` SDK due to deprecation.
- **structlog**: Already adopted as a shared library with SAGE. Outputs JSON logs compatible with Cloud Logging.
- **httpx**: Chosen as a modern, synchronous/async-capable HTTP client. Used for both MITRE CTI STIX bundle fetching and SAGE API calls. Unlike `requests`, httpx supports both sync and async with a unified interface.
- **fastapi**: Selected for the Web UI because it provides automatic OpenAPI generation, Pydantic v2 validation, and a clean path to a React SPA migration (REST endpoints are co-located with HTML routes).
- **uvicorn[standard]**: The de facto ASGI server for FastAPI; maintained by the same Encode team.
- **python-multipart**: Required by FastAPI/Starlette to handle `multipart/form-data` file uploads.
- **jinja2**: Minimal server-side templating for the Web UI. Chosen over a full JS framework to keep dependencies lean; the `/api/*` endpoints allow future React migration without server-side changes.
- **cryptography**: Not used directly by BEACON. Pinned to `>=46.0.7` to fix CVE-2026-39892 in the transitive dependency chain (`google-genai` → `httpcore` → `h11` → `cryptography`).
- **python-dotenv**: Loads `.env` files into `os.environ` at process startup. Keeps credentials and project-specific settings out of source code and shell profiles. Chosen over a custom `.env` parser to avoid reimplementing quoting, comment handling, and variable expansion.
- **click**: Chosen over argparse for the unified `beacon` CLI because click cleanly composes a `Group` of subcommands without re-parsing argv at every dispatcher boundary, has a first-class `CliRunner` for tests, and produces auto-formatted `--help` text. The legacy `cmd/*.py` modules keep their existing argparse-based entry points so the 1.x backward-compat path stays unchanged.

> **Removed in 0.9.0:** `markitdown[pdf]` was used only by `cmd/stix_from_report.py`,
> which has moved to TRACE. The dependency now lives in
> `TRACE/pyproject.toml`; see `TRACE/docs/dependencies.md` for its rationale.
