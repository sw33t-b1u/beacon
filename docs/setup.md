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
uv run python cmd/generate_pir.py \
  --context tests/fixtures/sample_context_manufacturing.json \
  --no-llm \
  --output output/pir_output.json \
  --collection-plan output/collection_plan.md
```

### Option B: LLM mode — Markdown input (requires GCP)

```bash
# Ensure GCP_PROJECT_ID is set and ADC is configured (see Step 4)
uv run python cmd/generate_pir.py \
  --context input/acme.md \
  --output output/pir_output.json \
  --collection-plan output/collection_plan.md
```

To also save the intermediate `BusinessContext` JSON for inspection or reuse:

```bash
uv run python cmd/generate_pir.py \
  --context input/acme.md \
  --save-context output/business_context.json
# Writes: output/pir_output.json, output/collection_plan.md, output/business_context.json
```

---

## Generating SAGE assets.json

Convert the `Critical Assets` section of your context document into a SAGE-compatible
`assets.json` for loading into Spanner.

```bash
# From Markdown (requires LLM / Vertex AI)
uv run python cmd/generate_assets.py --context input/context.md

# From JSON (no LLM required)
uv run python cmd/generate_assets.py \
  --context input/context.json \
  --no-llm \
  --output output/assets.json
```

The generated file is written to `output/assets.json`. Open it and fill in:

| Field | Action |
|-------|--------|
| `owner` | Team email or name per asset |
| `security_controls` | Define your EDR/SIEM/firewall entries |
| `security_control_ids` | Link assets to the controls above |
| `asset_vulnerabilities` | Populate after running STIX ETL |
| `actor_targets` | Populate after running STIX ETL |

Then load into SAGE Spanner (`load_assets.py` lives in `SAGE/cmd/`, so switch
directories first):

```bash
cd ../SAGE && uv run python cmd/load_assets.py --file ../BEACON/output/assets.json
```

---

## Generating SAGE identity_assets.json

Convert the `Identities and Access` section of the context document into
`identity_assets.json` (Initiative A). Each identity carries an `id`, `name`,
`role_tags`, `has_access` edges to one or more assets, and — from BEACON
0.13.0 — the Initiative C Phase 2 flag `is_high_value_impersonation_target`
plus the free-form `impersonation_risk_factors` list.

```bash
# Markdown context (requires LLM)
uv run python cmd/generate_identity_assets.py --context input/context.md

# JSON context (no LLM)
uv run python cmd/generate_identity_assets.py \
  --context input/context.json \
  --no-llm \
  --output output/identity_assets.json
```

Validate via TRACE (cross-references each `has_access[].asset_id` against
`assets.json`), then load into SAGE:

```bash
cd ../TRACE && uv run python cmd/validate_identity_assets.py \
  --identity-assets ../BEACON/output/identity_assets.json \
  --assets          ../BEACON/output/assets.json

cd ../SAGE  && uv run python cmd/load_identity_assets.py \
  --file ../BEACON/output/identity_assets.json
```

If the context document omits the identity section, the CLI emits an empty
artifact (`identities: []`, `has_access: []`) which TRACE accepts.

---

## Generating SAGE user_accounts.json

Convert the `User Accounts` section into `user_accounts.json`. Each entry
carries a `username`, optional `identity_id` linking back to
`identity_assets.json`, and `account_on_asset` edges describing which
accounts exist on which assets (used by SAGE for credential-flow analytics).

```bash
# Markdown context (requires LLM)
uv run python cmd/generate_user_accounts.py --context input/context.md

# JSON context (no LLM)
uv run python cmd/generate_user_accounts.py \
  --context input/context.json \
  --no-llm \
  --output output/user_accounts.json
```

Validate via TRACE, then load into SAGE:

```bash
cd ../TRACE && uv run python cmd/validate_user_accounts.py \
  --user-accounts ../BEACON/output/user_accounts.json \
  --assets        ../BEACON/output/assets.json

cd ../SAGE  && uv run python cmd/load_user_accounts.py \
  --file ../BEACON/output/user_accounts.json
```

---

## Extracting STIX bundles from CTI reports

> **Moved to TRACE in BEACON 0.9.0 (`cmd/stix_from_report.py` deleted in
> BEACON 0.10.0).** PDF / URL → STIX 2.1 extraction now lives in the
> sibling project [TRACE](../../TRACE/). Use `TRACE/cmd/crawl_single.py`
> instead. See `TRACE/docs/setup.md` and `TRACE/docs/beacon_handoff.md`
> for the new workflow.

---

## After Generation: Review and Export

1. **Validate** — moved to TRACE in BEACON 0.9.0 (`BEACON/cmd/validate_pir.py`
   was deleted in BEACON 0.10.0). The richer validator runs schema +
   referential checks (taxonomy presence, asset-tag match, validity window):

   ```bash
   cd ../TRACE && uv run python cmd/validate_pir.py --pir pir_output.json
   # Optionally combine with assets.json so asset_weight_rules are checked too:
   cd ../TRACE && uv run python cmd/validate_pir.py --pir pir_output.json --assets assets.json
   ```

2. **Review** — inspect and edit `pir_output.json` manually, or open the web dashboard:

   ```bash
   uv run beacon web   # http://localhost:8000 → PIR tab → review → export
   ```

3. **Submit for review** (optional) — use the web dashboard's **Settings** tab for
   pipeline approval workflows. The legacy GHE CLI is deprecated:

   ```bash
   # Deprecated since BEACON 1.1.0 — use the web dashboard instead
   uv run python cmd/submit_for_review.py --pir pir_output.json
   ```

4. **Deploy to SAGE** — copy the validated PIR to SAGE's `PIR_FILE_PATH` and run ETL:

   ```bash
   cp pir_output.json /path/to/sage/config/pir.json
   # Then run SAGE ETL (see docs/operations.md — SAGE Integration section)
   ```

---

## Updating the Threat Taxonomy

`schema/threat_taxonomy.json` is fully auto-generated from MITRE ATT&CK Enterprise and MISP Galaxy. Run the updater to rebuild the file end-to-end:

```bash
# Preview changes without writing to disk
uv run python -m cmd.update_taxonomy --dry-run

# Apply updates
uv run python -m cmd.update_taxonomy
```

Options:

- `--mitre-url` / `--misp-url` — override the upstream URLs (defaults point at the canonical GitHub raw endpoints recorded in `_metadata.sources`).
- `--mitre-cache` / `--misp-cache` — read from a local copy instead of fetching (useful for air-gapped runs); the canonical URLs are still written to `_metadata.sources`.

> Any hand-edits to the JSON will be overwritten on the next run. If a new actor or tag vocabulary is needed, submit it upstream to MITRE/MISP or extend the updater logic, not the JSON.

---

## Web Dashboard

```bash
uv run beacon web   # default http://localhost:8000
```

Open `http://localhost:8000` in your browser.

The dashboard is organized into five tabs:

| Tab | Description |
|-----|-------------|
| **Dashboard** | Pipeline summary: PIR count, collection status, choke-points from SAGE |
| **PIR** | Generate PIR from a context document; review and export output; auto-loads the latest artifact from StorageBackend |
| **Collection** | Run TRACE `crawl-single` / `crawl-batch` as a subprocess directly from the browser (requires `TRACE_ROOT_PATH`) |
| **Threats** | Proxy to the SAGE Analysis API: actor search, TTP lookup, threat-summary (requires `SAGE_API_URL`) |
| **Settings** | Configure storage mode, SAGE URL, TRACE path; changes are persisted to `.beacon_settings.json` |

**PIR tab** provides two workflows:
- **Generate from business context** — Upload a context document, choose LLM or dictionary-only mode.
- **Load existing PIR JSON** — Upload a previously generated `pir_output.json` for review without re-running the pipeline.

> **Deprecated:** `cmd/submit_for_review.py` (GHE Issue creation) is deprecated as of
> BEACON 1.1.0 and will be removed in a future release. Use the Settings tab for
> pipeline approval workflows.

---

## Step 7 — Deploy Web Dashboard to Cloud Run

Build the container image and deploy the BEACON web UI as a Cloud Run Service with IAP protection.

```sh
# Load .env if not already sourced
source .env
export IMAGE=gcr.io/${GCP_PROJECT_ID}/beacon-web

# Build and push container image via Cloud Build
gcloud builds submit --tag ${IMAGE} --project=${GCP_PROJECT_ID}

# Deploy as a Cloud Run Service (always-on, no public access)
gcloud run deploy beacon-web \
  --image=${IMAGE} \
  --region=${VERTEX_LOCATION:-us-central1} \
  --no-allow-unauthenticated \
  --port=8000 \
  --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},VERTEX_LOCATION=${VERTEX_LOCATION:-us-central1},BEACON_STORAGE=${BEACON_STORAGE:-gcs},BEACON_GCS_BUCKET=${BEACON_GCS_BUCKET},SAGE_API_URL=${SAGE_API_URL}" \
  --set-secrets="BEACON_GCS_PREFIX=beacon-gcs-prefix:latest" \
  --project=${GCP_PROJECT_ID}
```

> **Secret Manager:** Store sensitive values with
> `gcloud secrets create beacon-gcs-prefix --data-file=- <<< "prod/"` and
> reference with `--set-secrets` instead of `--set-env-vars`.

> **Service account:** Create a dedicated service account and grant
> `roles/aiplatform.user` (Vertex AI Gemini), `roles/storage.objectAdmin`
> (GCS artifacts), and `roles/run.invoker` before deploying.
>
> ```sh
> gcloud iam service-accounts create beacon-web \
>   --display-name="BEACON Web Service" \
>   --project=${GCP_PROJECT_ID}
>
> for ROLE in roles/aiplatform.user roles/storage.objectAdmin roles/run.invoker; do
>   gcloud projects add-iam-policy-binding ${GCP_PROJECT_ID} \
>     --member="serviceAccount:beacon-web@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
>     --role="${ROLE}"
> done
>
> gcloud run services update beacon-web \
>   --service-account="beacon-web@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
>   --region=${VERTEX_LOCATION:-us-central1} \
>   --project=${GCP_PROJECT_ID}
> ```

> **IAP protection:** Enable Identity-Aware Proxy on the Cloud Run service to
> restrict access to authorized users only. The service is deployed with
> `--no-allow-unauthenticated`; combine with Cloud IAP + Internal Load Balancer
> for VPC-internal access without a public IP.

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
