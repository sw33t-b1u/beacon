# BEACON — Setup Guide

Japanese translation: [`docs/ja/setup.md`](ja/setup.md)

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
cd beacon/BEACON
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
| `GHE_TOKEN` | GHE review | — | GitHub / GHE Personal Access Token |
| `GHE_REPO` | GHE review | — | `owner/repo` format |
| `GHE_API_BASE` | No | `https://api.github.com` | Override for self-hosted GHE |
| `SAGE_API_URL` | SAGE mode | — | SAGE Analysis API URL |

`GCP_PROJECT_ID` is **not required** when using `--no-llm` mode.

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

### Option A: No-LLM mode (JSON input, no GCP required)

Use when you already have a `business_context.json` and want to avoid LLM costs.

```bash
uv run python cmd/generate_pir.py \
  --context tests/fixtures/sample_context_manufacturing.json \
  --no-llm \
  --output pir_output.json \
  --collection-plan collection_plan.md
```

### Option B: LLM mode — Markdown input (requires GCP)

Use when your business context is a strategy document in Markdown format.
The LLM converts the Markdown into a structured `BusinessContext` and enriches the PIR output.

```bash
# Ensure GCP_PROJECT_ID is set and ADC is configured (see Step 4)
uv run python cmd/generate_pir.py \
  --context your_strategy_doc.md \
  --output pir_output.json \
  --collection-plan collection_plan.md
```

### Option C: LLM mode — JSON input

Use when you have a JSON context file and want LLM-enriched descriptions and collection focus.

```bash
uv run python cmd/generate_pir.py \
  --context your_context.json \
  --output pir_output.json \
  --collection-plan collection_plan.md
```

---

## After Generation: Review and Export

1. **Validate** — check that the output conforms to the SAGE-compatible PIR schema:

   ```bash
   uv run python cmd/validate_pir.py --pir pir_output.json
   ```

2. **Review** — inspect and edit `pir_output.json` manually, or use the Web UI:

   ```bash
   uv run python cmd/web_app.py --port 8080
   # Open http://localhost:8080 → upload context → review → export
   ```

3. **Submit for GHE review** (optional) — create GitHub Issues for analyst sign-off:

   ```bash
   uv run python cmd/submit_for_review.py --pir pir_output.json
   ```

4. **Deploy to SAGE** — copy the validated PIR to SAGE's `PIR_FILE_PATH` and run ETL:

   ```bash
   cp pir_output.json /path/to/sage/config/pir.json
   # Then run SAGE ETL (see docs/sage_integration.md)
   ```

---

## Web UI (optional)

```bash
uv run python cmd/web_app.py --port 8080
```

Open `http://localhost:8080` in your browser.

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
