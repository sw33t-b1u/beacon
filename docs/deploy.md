# BEACON — Cloud Run Deployment

Japanese translation: [`docs/deploy.ja.md`](deploy.ja.md)

Before deploying, complete [docs/setup.md](setup.md). Ensure `make check` passes before deploying.

---

## Cross-repo deploy order

BEACON, SAGE, and TRACE form a cycle at deploy time: BEACON needs
`SAGE_API_URL` (the sage-api URL) and SAGE's ETL needs the validated
`pir.json` BEACON produces. Break the cycle in this order — an unmet
dependency is wired in afterward with `--update-env-vars`, so BEACON does
not block on a `sage-api` URL that does not exist yet. This sequence
matches [SAGE deploy.md](../../sage/docs/deploy.md); the two repos agree.

1. **SAGE — deploy `sage-api` first** (plus its GCS bucket). The API starts
   even with no database, so its URL exists before BEACON needs it.
2. **BEACON — deploy `beacon-web`.** Wire `SAGE_API_URL` to the sage-api URL
   from step 1, and have SAGE grant BEACON's service account (`beacon-sa`)
   `roles/run.invoker` on `sage-api` (see [SAGE integration](#sage-integration-cross-repo)).
3. **BEACON — generate PIR / assets.** Produce `pir_output.json` and the
   asset artifacts from business context.
4. **TRACE — validate.** Pass the assets, PIR, and any STIX bundles through
   TRACE, the single validation gate for all SAGE inputs. See the
   [TRACE repo](https://github.com/sw33t-b1u/trace) for the commands (not
   duplicated here).
5. **SAGE — load and run ETL.** Place the validated artifacts in GCS, then
   run `sage-etl`.

If `sage-api` is not yet deployed when BEACON goes out, deploy `beacon-web`
without `SAGE_API_URL` and add it later via `--update-env-vars` (see
[`SAGE_API_URL` (optional)](#day-1-initial-deploy) and Day-N Redeploy).

---

## Day-0 Prerequisites

### Enable APIs

```sh
source .env
export REGION=${VERTEX_LOCATION:-us-central1}

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  --project=${GCP_PROJECT_ID}
```

### Create Artifact Registry repository

```sh
gcloud artifacts repositories create cloud-run \
  --repository-format=docker \
  --location=${REGION} \
  --project=${GCP_PROJECT_ID}
```

### Create service account and grant IAM roles

Create the `beacon-sa` service account and bind the required roles before running any deploy commands that reference it.

```sh
gcloud iam service-accounts create beacon-sa \
  --display-name="BEACON Web Service" \
  --project=${GCP_PROJECT_ID}

for ROLE in roles/aiplatform.user roles/storage.objectAdmin roles/run.invoker; do
  gcloud projects add-iam-policy-binding ${GCP_PROJECT_ID} \
    --member="serviceAccount:beacon-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
    --role="${ROLE}"
done
```

> **IAM roles explained:**
> - `roles/aiplatform.user` — Vertex AI Gemini access for LLM-driven analysis
> - `roles/storage.objectAdmin` — read/write GCS artifacts (BEACON_STORAGE_BUCKET)
> - `roles/run.invoker` — allows BEACON to call SAGE Analysis API (`sage-api`) via OIDC

### Create GCS bucket (if not already existing)

```sh
# Storage backend bucket (only when BEACON_STORAGE=gcs)
gcloud storage buckets create gs://${BEACON_STORAGE_BUCKET} \
  --location=${REGION} \
  --project=${GCP_PROJECT_ID}
```

---

## Day-1 Initial Deploy

### beacon-web (Cloud Run Service)

```sh
source .env
export REGION=${VERTEX_LOCATION:-us-central1}

# (Optional) Capture SAGE Analysis API URL if already deployed
export SAGE_API_URL=$(gcloud run services describe sage-api \
  --region=${REGION} --format='value(status.url)' --project=${GCP_PROJECT_ID} 2>/dev/null || echo "")

export IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/cloud-run/beacon-web

# Build and push container image via Cloud Build
gcloud builds submit --tag ${IMAGE} --project=${GCP_PROJECT_ID}

# Deploy as Cloud Run Service
gcloud run deploy beacon-web \
  --image=${IMAGE} \
  --region=${REGION} \
  --no-allow-unauthenticated \
  --port=8000 \
  --service-account="beacon-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},VERTEX_LOCATION=${REGION},BEACON_STORAGE=gcs,BEACON_STORAGE_BUCKET=${BEACON_STORAGE_BUCKET},BEACON_STORAGE_PREFIX=${BEACON_STORAGE_PREFIX:-prod/}${SAGE_API_URL:+,SAGE_API_URL=${SAGE_API_URL}}" \
  --project=${GCP_PROJECT_ID}
```

> **`--set-env-vars` vs `--update-env-vars`:** The initial deploy uses `--set-env-vars` to set the full env-var set in one shot. Subsequent changes must use `--update-env-vars` (see Day-N). Using `--set-env-vars` on an existing service **replaces the entire env-var set**, silently dropping any key not re-listed.

> **`SAGE_API_URL` (optional):** If `sage-api` was not yet deployed when BEACON was first deployed, add it later using `--update-env-vars` (see Day-N Redeploy below). This is the "wire it later" branch of the [Cross-repo deploy order](#cross-repo-deploy-order) — deploy `sage-api` first when you can, otherwise wire `SAGE_API_URL` afterward.

---

## Day-N Redeploy

### Code-only changes

Use this flow when only the container image changes (no env-var additions or removals).

```sh
export IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/cloud-run/beacon-web

# Rebuild and push the new image
gcloud builds submit --tag ${IMAGE} --project=${GCP_PROJECT_ID}

# Update the Cloud Run Service
gcloud run services update beacon-web \
  --image=${IMAGE} \
  --region=${REGION} \
  --project=${GCP_PROJECT_ID}
```

### Env-var changes on an existing revision

Use `--update-env-vars` and `--remove-env-vars` — **not** `--set-env-vars`, which replaces the entire env-var set and silently drops any key not re-listed.

```sh
# Add or update a single variable without touching others
gcloud run services update beacon-web \
  --update-env-vars=NEW_VAR=value \
  --region=${REGION} \
  --project=${GCP_PROJECT_ID}

# Remove an old variable at the same time
gcloud run services update beacon-web \
  --update-env-vars=NEW_VAR=value \
  --remove-env-vars=OLD_VAR \
  --region=${REGION} \
  --project=${GCP_PROJECT_ID}

# Add SAGE_API_URL after sage-api is deployed
gcloud run services update beacon-web \
  --update-env-vars="SAGE_API_URL=$(gcloud run services describe sage-api --region=${REGION} --format='value(status.url)' --project=${GCP_PROJECT_ID})" \
  --region=${REGION} \
  --project=${GCP_PROJECT_ID}
```

> **Verify:** `gcloud run services describe beacon-web --region=${REGION} --format="value(spec.template.spec.containers[0].env[].name)" --project=${GCP_PROJECT_ID}`

---

## Operating BEACON (analyst workflow)

The Day-0/1/N sections above stand up the infrastructure. This section
explains what a CTI analyst actually *does* with a GCS-backed BEACON
deployment, and in what order. Read the **Overview** first to grasp the whole
pipeline; the **Detailed commands** block at the end walks the same steps with
real commands.

### Overview — what you accomplish

Following this flow takes a fresh business-context document all the way to
queryable attack paths. Each step exists for a reason:

- **Author business context** — describe the organization (industry, geography,
  crown jewels, regulatory context) in `input/context.md`. This is the single
  input that drives every downstream score; without it BEACON has nothing to
  prioritize against.
- **Generate PIR + assets** — BEACON converts that context into Priority
  Intelligence Requirements plus three asset drafts (`assets`,
  `identity_assets`, `user_accounts`). This turns prose into the structured,
  scored artifacts SAGE and TRACE consume.
- **Artifacts persist to GCS** — when the storage backend is `gcs`, every
  generated and saved artifact lands in the configured bucket/prefix instead of
  the local `output/` directory. This is what lets a Cloud Run revision (which
  has no durable local disk) share state across requests and with the rest of
  the pipeline.
- **Review / edit in the web dashboard** — open the dashboard and complete the
  org-known fields that no LLM can know (asset owners, security controls, CVE
  mappings, identity/account flags), then re-save. This is the human-in-the-loop
  gate before anything reaches the graph.
- **TRACE validates** — every SAGE input passes through TRACE, the single
  validation gate. This catches schema and referential errors (taxonomy gaps,
  asset-tag mismatches, expired validity windows) before they corrupt the graph.
- **SAGE ingests into the graph** — SAGE loads the validated assets and runs the
  STIX ETL, filtering threat actors by your PIR tags and computing
  `pir_adjusted_criticality`. This is where external CTI and internal context
  finally meet.
- **Query attack paths** — with the graph populated, query SAGE (Analysis API,
  visualizer, or the dashboard **Threats** tab) for actor coverage, TTPs, and
  the assets most at risk. This is the payoff: prioritized attack-path insight
  for Red/Blue/IR teams.

From that overview alone an analyst can see what is possible — author context,
produce scored artifacts, persist them to GCS, refine them in the browser,
validate, ingest, and finally query — without reading a single command.

### Storage backend selection (GCS vs local)

Where artifacts persist is decided by the storage backend, which is resolved
from two sources with this precedence:

**`defaults < .beacon_settings.json (Settings UI) < environment variables`** —
environment variables always win.

- **Environment variables** — set `BEACON_STORAGE=gcs`,
  `BEACON_STORAGE_BUCKET=<bucket>`, and `BEACON_STORAGE_PREFIX=<prefix>` on the
  Cloud Run revision (the Day-1 deploy already does this). This is the
  recommended production path.
- **Web Settings tab** — choosing storage mode `gcs` (with bucket/prefix) in the
  dashboard **Settings** tab persists those values to `.beacon_settings.json`.
  As of BEACON 4.1.0 this choice is honored by **all** data paths — PIR and
  asset load/save now respect the Settings-UI selection even when no
  `BEACON_STORAGE` environment variable is set. (Earlier releases ignored the
  Settings value for data load unless the env var was also present.)

Because env vars sit at the top of the precedence chain, a `BEACON_STORAGE` set
on the Cloud Run revision overrides whatever the Settings UI saved. On a Cloud
Run deployment the recommendation is therefore to let the revision's env vars be
authoritative and use the Settings tab mainly for local/standalone runs.

> **GCS access requirements:** the runtime service account
> (`beacon-sa`) needs `roles/storage.objectAdmin` on the bucket (granted in
> Day-0), the bucket must exist (Day-0), and the `gcs` extra
> (`google-cloud-storage`) must be installed in the image. With those in place,
> no analyst-side credential handling is needed — Cloud Run injects the service
> account identity.

### Detailed commands

The same flow with actual commands. CLI invocations use `uv run`; cross-repo
steps assume sibling `../TRACE` and `../SAGE` checkouts.

```bash
# 1. Author business context (edit the input document)
#    input/context.md  — industry, geography, crown jewels, regulatory context

# 2. Generate PIR + the three asset drafts (single pass)
uv run beacon pir-generate                    # uses input/context.md
#    Emits pir_output.json plus assets_<ts>.json, identity_assets_<ts>.json,
#    user_accounts_<ts>.json. With BEACON_STORAGE=gcs these land in the bucket.

# 3. Review / edit in the dashboard (org-known fields the LLM cannot fill)
uv run beacon web                             # http://localhost:8000
#    PIR tab      — review scores, approve PIRs
#    Assets tab   — owner, security_control_ids, security_controls,
#                   asset_vulnerabilities (CVE → asset_id)
#    Identity tab — identity descriptions, roles, impersonation flags
#    Accounts tab — account type, privilege flags, account_on_asset edges
#    Settings tab — storage mode / bucket / prefix, SAGE URL, TRACE path
#    Re-save each tab to write a fresh <type>_<ts>.json to the backend.

# 4. Validate every SAGE input through TRACE (the single validation gate)
cd ../TRACE && uv run trace validate-pir --pir pir_output.json
cd ../TRACE && uv run trace validate-pir --pir pir_output.json --assets assets.json

# 5. Ingest into the SAGE graph
cd ../SAGE && uv run sage load-assets --input output/assets.json
cd ../SAGE && uv run sage run-etl

# 6. Query attack paths
cd ../SAGE && uv run sage visualize-graph     # interactive HTML
#    Or use the dashboard Threats tab (SAGE API proxy: actor search,
#    TTP lookup, threat-summary).
```

For the full per-step detail (PIR fields, asset-tab editing, ETL verification,
troubleshooting), see [docs/usage.md](usage.md) and
[docs/pipeline-guide.md](pipeline-guide.md).

---

## Access (Production = L2)

`--no-allow-unauthenticated` is already set during deploy. Grant `roles/run.invoker` to the identities that need access.

### Grant invoke permission

```sh
# Single user
gcloud run services add-iam-policy-binding beacon-web \
  --region=${REGION} \
  --member="user:alice@example.com" \
  --role=roles/run.invoker \
  --project=${GCP_PROJECT_ID}

# Google Group (recommended for teams)
gcloud run services add-iam-policy-binding beacon-web \
  --region=${REGION} \
  --member="group:beacon-users@example.com" \
  --role=roles/run.invoker \
  --project=${GCP_PROJECT_ID}
```

### Browser access

```sh
gcloud run services proxy beacon-web --region=${REGION} --project=${GCP_PROJECT_ID}
# Open http://localhost:8080/dashboard
```

The proxy automatically injects the developer's identity token. No bearer token management needed.

### Verify via curl

```sh
URL=$(gcloud run services describe beacon-web \
  --region=${REGION} \
  --format='value(status.url)' \
  --project=${GCP_PROJECT_ID})

curl -sL -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -w "\nHTTP=%{http_code}\n" \
  ${URL}/dashboard | head -10
```

Expected: `HTTP=200` and HTML containing `<title>BEACON — Dashboard</title>`.

### SAGE integration (cross-repo)

BEACON's service account (`beacon-sa`) must have `roles/run.invoker` on `sage-api` to call the SAGE Analysis API. Grant this from the SAGE side:

```sh
gcloud run services add-iam-policy-binding sage-api \
  --region=${REGION} \
  --member="serviceAccount:beacon-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role=roles/run.invoker \
  --project=${GCP_PROJECT_ID}
```

See [SAGE deploy.md](../../sage/docs/deploy.md) for the full SAGE deploy procedure.

---

## Out of scope

IAP / Internal Load Balancer / VPC Service Controls are not configured by this guide. For small Google Workspace user counts (a few users), the L2 IAM binding above is sufficient. If you need context-aware access or custom network topology, see https://cloud.google.com/iap/docs.

---

## CTI Platform console topology (recommended for browser-complete operation)

For the browser workflow where Collection can call TRACE and Threats can call
SAGE, deploy a combined **CTI Platform** Cloud Run service that contains BEACON
web and the TRACE CLI in one image. Keep SAGE ETL as a separate Cloud Run Job
(single writer), and run `sage-api` as the read-only analysis API.

Recommended components:

| Component | Cloud Run type | Purpose |
|-----------|----------------|---------|
| `cti-console` | service | BEACON web UI + TRACE CLI subprocess (`TRACE_ROOT_PATH=/app/trace`) |
| `sage-api` | service | Read-only SAGE Analysis API used by the Threats tab |
| `sage-etl` | job | Single-writer ETL that updates `db/sage.db` in shared GCS storage |

Build the combined console image from the repository root (one level above the
`beacon/` and `trace/` directories):

```bash
export IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/cloud-run/cti-console

gcloud builds submit . \
  --config=beacon/cloudbuild.cti-console.yaml \
  --ignore-file=beacon/.gcloudignore.cti-console \
  --substitutions=_IMAGE=${IMAGE} \
  --project=${GCP_PROJECT_ID}
```

Deploy the console service with the SAGE API URL and shared storage settings:

```bash
gcloud run deploy cti-console \
  --image=${IMAGE} \
  --region=${REGION} \
  --project=${GCP_PROJECT_ID} \
  --service-account="beacon-web@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars="TRACE_ROOT_PATH=/app/trace,SAGE_API_URL=${SAGE_API_URL},BEACON_STORAGE=gcs,BEACON_STORAGE_BUCKET=${STORAGE_BUCKET},BEACON_STORAGE_PREFIX=${STORAGE_PREFIX}"
```

`TRACE_ROOT_PATH=/app/trace` is set in the image and can be overridden. The
existing BEACON-only image remains available for deployments that do not need
Collection to execute TRACE from the browser.
