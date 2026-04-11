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

Place your strategy document as `input/context.md` (see [`docs/context_template.md`](context_template.md) for the template). The `input/` and `output/` directories are gitignored — they contain sensitive data and must not be committed.

### Option A: No-LLM mode (JSON input, no GCP required)

Use when you already have a `business_context.json` and want to avoid LLM costs.

```bash
uv run python cmd/generate_pir.py \
  --context tests/fixtures/sample_context_manufacturing.json \
  --no-llm \
  --output output/pir_output.json \
  --collection-plan output/collection_plan.md
```

### Option B: LLM mode — Markdown input (default, requires GCP)

Drop your strategy document as `input/context.md`, then run without arguments:

```bash
# Ensure GCP_PROJECT_ID is set and ADC is configured (see Step 4)
uv run python cmd/generate_pir.py
# Reads:  input/context.md
# Writes: output/pir_output.json, output/collection_plan.md
```

To also save the intermediate `BusinessContext` JSON for inspection or reuse:

```bash
uv run python cmd/generate_pir.py --save-context
# Writes: output/pir_output.json, output/collection_plan.md, output/business_context.json
```

### Option C: LLM mode — JSON input

Use when you have a JSON context file and want LLM-enriched descriptions and collection focus.

```bash
uv run python cmd/generate_pir.py \
  --context your_context.json \
  --output output/pir_output.json \
  --collection-plan output/collection_plan.md
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

## Updating the Threat Taxonomy

`schema/threat_taxonomy.json` maps industries, geographies, and business triggers to threat actor tags. It is maintained in two ways:

**Automatic update** — syncs `mitre_groups` and `priority_ttps` from the MITRE ATT&CK STIX bundle:

```bash
# Preview changes without writing to disk
uv run python -m cmd.update_taxonomy --dry-run

# Apply updates
uv run python -m cmd.update_taxonomy
```

**Manual update** — edit `schema/threat_taxonomy.json` directly for:
- Adding new actor categories or nations
- Tuning `target_industries` / `target_geographies`
- Updating `geography_threat_map`, `industry_threat_map`, `business_trigger_map`

> The automatic update does **not** touch manually managed sections. Run it periodically (e.g. quarterly) to keep MITRE group names and TTP IDs current.

**Updating the `threat_tag_completion.md` whitelist** — when the LLM fallback path is active (dictionary finds zero matches), `src/beacon/llm/prompts/threat_tag_completion.md` constrains the group names the LLM may suggest. The whitelist in that file is maintained manually using these reference sources:

| Source | What to update |
|--------|---------------|
| [MITRE ATT&CK Groups](https://attack.mitre.org/groups/) | Nation-state and criminal group canonical names |
| [MISP Galaxy threat-actor cluster](https://github.com/MISP/misp-galaxy) | Aliases, new emerging actors |
| [BushidoUK Ransomware Tool Matrix](https://github.com/BushidoUK/Ransomware-Tool-Matrix) | Active RaaS and ransomware group names |

Edit the `## Notable Group Reference` section in `threat_tag_completion.md` to add or retire groups. Keep it in sync with the actor categories in `threat_taxonomy.json`.

---

## Web UI (optional)

```bash
uv run python cmd/web_app.py --port 8080
```

Open `http://localhost:8080` in your browser.

The Web UI provides two workflows:

**Generate from business context** — Upload a `business_context.json` or Markdown strategy document. Choose between:
- **Dictionary only** (no LLM, no GCP required) — fast, rule-based PIR generation
- **LLM mode** (requires GCP) — enriched descriptions, rationale, and collection focus via Google Gen AI (Gemini). When LLM mode is selected, you can override the default models for each complexity tier (simple / medium / complex) directly in the UI; leave blank to use the `.env` defaults.

**Load existing PIR JSON** — Upload a previously generated `pir_output.json` to review, edit, and re-export without re-running the pipeline.

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
