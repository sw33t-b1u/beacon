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
