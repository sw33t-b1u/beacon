# BEACON — Setup Guide

Japanese translation: [`docs/setup.ja.md`](setup.ja.md)

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | Required by `pyproject.toml` |
| [uv](https://docs.astral.sh/uv/) | latest | Virtual environment and package manager |
| GCP project | — | Required for LLM mode only |
| Git | 2.x+ | For hook installation |

---

## Step 1: Clone and install dependencies

```bash
git clone https://github.com/sw33t-b1u/beacon.git
cd beacon
uv sync --extra dev
```

---

## Step 2: Install Git hooks

```bash
make setup
```

This runs `git config core.hooksPath .githooks` and enables:

- **pre-commit** — runs `make vet lint` before every commit
- **pre-push** — runs `make check` (full quality gate) before every push

---

## Step 3: Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GCP_PROJECT_ID` | LLM mode | — | GCP project ID |
| `VERTEX_LOCATION` | No | `us-central1` | Vertex AI region |
| `BEACON_LLM_SIMPLE` | No | `gemini-2.5-flash-lite` | Simple task model |
| `BEACON_LLM_MEDIUM` | No | `gemini-2.5-flash` | Medium task model |
| `BEACON_LLM_COMPLEX` | No | `gemini-2.5-pro` | Complex reasoning model |
| `GHE_TOKEN` | No (deprecated) | — | GitHub / GHE Personal Access Token (`submit_for_review.py` — deprecated in 1.1.0) |
| `GHE_REPO` | No (deprecated) | — | `owner/repo` format (deprecated in 1.1.0) |
| `GHE_API_BASE` | No | `https://api.github.com` | Override for self-hosted GHE |
| `SAGE_API_URL` | SAGE mode | — | SAGE Analysis API URL (also configurable via Settings tab) |
| `BEACON_STORAGE` | No | `local` | Storage backend: `local` or `gcs` |
| `BEACON_STORAGE_BASE_DIR` | No | `output/` | Base directory for `local` backend |
| `BEACON_GCS_BUCKET` | GCS mode | — | GCS bucket name (required when `BEACON_STORAGE=gcs`) |
| `BEACON_GCS_PREFIX` | No | (empty) | Key prefix within the GCS bucket |
| `TRACE_ROOT_PATH` | No | — | Absolute path to TRACE repo root (enables Collection tab in dashboard) |

`GCP_PROJECT_ID` is **not required** when using `--no-llm` mode.

---

## Step 3b: Configure StorageBackend (optional)

By default, artifacts are written to `output/` (local backend). To use Google Cloud
Storage instead:

```bash
# Install the optional GCS dependency
uv sync --extra gcs

# Set env vars (or configure via the Settings tab in the web dashboard)
export BEACON_STORAGE=gcs
export BEACON_GCS_BUCKET=my-beacon-artifacts
export BEACON_GCS_PREFIX=prod/   # optional; defaults to empty string
```

Artifacts are stored with the filename pattern `<category>_<YYYYMMDDHHmm>.json`.
To revert to local storage: `export BEACON_STORAGE=local`.

---

## Step 4: Authenticate with GCP (LLM mode only)

```bash
gcloud auth application-default login
```

This sets up Application Default Credentials (ADC) used by Vertex AI. No API key management required.

---

## Step 5: Verify setup

```bash
# Run unit tests (no GCP required)
make test

# Run full quality gate
make check
```

---

## PIR Generation Workflow

Place your strategy document in `input/` (see [`schema/context_template.md`](../schema/context_template.md) for the template). The `input/` and `output/` directories are gitignored — they contain sensitive data and must not be committed.

`--context` is required. You specify the path explicitly, so any filename is accepted (e.g. `input/acme.md`, `input/context_2026Q2.md`).

### Option A: No-LLM mode (JSON input, no GCP required)

Use when you already have a `business_context.json` and want to avoid LLM costs.

```bash
beacon pir-generate \
  --context tests/fixtures/sample_context_manufacturing.json \
  --output-dir output/
```

### Option B: LLM mode — Markdown input (requires GCP)

```bash
# Ensure GCP_PROJECT_ID is set and ADC is configured (see Step 4)
beacon pir-generate \
  --context input/acme.md \
  --output-dir output/
```

To also save the intermediate `BusinessContext` JSON for inspection or reuse:

```bash
beacon pir-generate \
  --context input/acme.md \
  --save-context output/business_context.json
# Writes: output/pir_output.json, output/collection_plan.md, output/business_context.json
```

---

## Testing

No external services are required — MISP is mocked and SAGE is optional.

### Running tests

```bash
# Full quality gate (lint + test + audit)
make check

# Tests only
make test

# Or directly via uv
uv run pytest

# Verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_element_extractor.py

# Run a specific test class or method
uv run pytest tests/test_element_extractor.py::TestTriggerDetection
uv run pytest tests/test_element_extractor.py::TestTriggerDetection::test_cloud_dependency
```

### Test fixtures

Sample input files live under `tests/fixtures/`:

```
tests/fixtures/
├── sample_context.json      # Minimal BusinessContext for unit tests
├── sample_context.md        # Markdown business context example
└── ...                      # Additional scenario-specific fixtures
```

Use fixtures in tests via the standard `pytest` fixture mechanism or by loading
them directly:

```python
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

def test_something():
    ctx = json.loads((FIXTURES / "sample_context.json").read_text())
    ...
```

### No external services required

| Service | Behaviour in tests |
|---------|-------------------|
| MISP | Not called — all threat-taxonomy data is loaded from `schema/threat_taxonomy.json` |
| SAGE | Optional — use `_StubSageClient` to avoid real API calls |
| Vertex AI / Gemini | Not called — tests use `--no-llm` paths or mock the client |
| GCS | Not called — storage defaults to `local` in tests |

### Common test patterns

**Stub SAGE client:**

```python
from beacon.sage.client import _StubSageClient

client = _StubSageClient()
# Returns empty actor lists; safe for unit tests that exercise scoring logic
```

**Web app session fixtures:**

Tests for the FastAPI web app use `httpx.AsyncClient` with an `ASGITransport`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from beacon.web.app import app

@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
```

**LLM-disabled pipeline test:**

Pass `use_llm=False` when constructing pipeline objects, or set the env var:

```bash
BEACON_NO_LLM=1 uv run pytest
```

### Lint

```bash
make vet      # ruff check (fast)
make lint     # ruff format --check
make format   # ruff format + fix (auto-corrects)
```

---

## Security scanning

```bash
make audit
```

Runs `pip-audit` to check for known vulnerabilities in dependencies. Included in `make check`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `GCP_PROJECT_ID not set` error | LLM mode without GCP config | Use `--no-llm` or set `GCP_PROJECT_ID` |
| `pip-audit` findings | Vulnerable dependency | Update the dependency version in `pyproject.toml` |
| Hook not running | `make setup` not executed | Run `make setup` in the BEACON directory |
