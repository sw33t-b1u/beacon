# BEACON — Cloud Run Deployment

Japanese translation: [`docs/deploy.ja.md`](deploy.ja.md)

Before deploying, complete the environment setup described in [docs/setup.md](setup.md). The SAGE Analysis API (`sage-api`) should be deployed first if you intend to use the Threats tab — see [SAGE deploy.md](../../sage/docs/deploy.md) Step 10.

---

## Step 1 — Deploy BEACON Web Dashboard to Cloud Run

Build and deploy the BEACON web UI as a Cloud Run Service.

```sh
# Load .env if not already sourced
source .env
export REGION=${VERTEX_LOCATION:-us-central1}

# (Optional) Capture SAGE Analysis API URL if already deployed
export SAGE_API_URL=$(gcloud run services describe sage-api \
  --region=${REGION} --format='value(status.url)' --project=${GCP_PROJECT_ID} 2>/dev/null || echo "")

# Create Artifact Registry repository (first time only)
gcloud artifacts repositories create cloud-run \
  --repository-format=docker \
  --location=${REGION} \
  --project=${GCP_PROJECT_ID}

export IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/cloud-run/beacon-web

# Build and push container image
gcloud builds submit --tag ${IMAGE} --project=${GCP_PROJECT_ID}

# Deploy as Cloud Run Service
gcloud run deploy beacon-web \
  --image=${IMAGE} \
  --region=${REGION} \
  --no-allow-unauthenticated \
  --port=8000 \
  --service-account="beacon-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},VERTEX_LOCATION=${REGION},BEACON_STORAGE=gcs,BEACON_GCS_BUCKET=${BEACON_GCS_BUCKET},BEACON_GCS_PREFIX=prod/${SAGE_API_URL:+,SAGE_API_URL=${SAGE_API_URL}}" \
  --project=${GCP_PROJECT_ID}
```

> **`--set-env-vars` vs `--update-env-vars`:** Subsequent invocations of `gcloud run services update --set-env-vars=...` **replace** the entire env-var set, silently dropping any keys not re-listed. To merge, use `--update-env-vars=KEY=VAL` instead. Verify with `gcloud run services describe beacon-web --format="value(spec.template.spec.containers[0].env[].name)"` after every update.

> **Service account:** Create a dedicated `beacon-sa` service account and grant `roles/aiplatform.user` (Vertex AI Gemini), `roles/storage.objectAdmin` (GCS artifacts), and `roles/run.invoker` (so Cloud Scheduler or BEACON-to-SAGE auth works) before deploying.
>
> ```sh
> gcloud iam service-accounts create beacon-sa \
>   --display-name="BEACON Web Service" \
>   --project=${GCP_PROJECT_ID}
>
> for ROLE in roles/aiplatform.user roles/storage.objectAdmin roles/run.invoker; do
>   gcloud projects add-iam-policy-binding ${GCP_PROJECT_ID} \
>     --member="serviceAccount:beacon-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
>     --role="${ROLE}"
> done
> ```

> **Secret Manager (optional):** For production, store sensitive values such as `BEACON_GCS_PREFIX` in Secret Manager and reference with `--set-secrets="BEACON_GCS_PREFIX=beacon-gcs-prefix:latest"` instead of `--set-env-vars`. The example above uses env-var directly for PoC simplicity.

> **Connecting to SAGE Analysis API:** If `sage-api` was not yet deployed when BEACON was first deployed, set `SAGE_API_URL` later using the merge-form update:
> ```sh
> gcloud run services update beacon-web \
>   --region=${REGION} \
>   --update-env-vars="SAGE_API_URL=$(gcloud run services describe sage-api --region=${REGION} --format='value(status.url)' --project=${GCP_PROJECT_ID})" \
>   --project=${GCP_PROJECT_ID}
> ```

---

## Step 2 — Grant access & verify

The service is deployed with `--no-allow-unauthenticated`, so initial access requires an IAM binding.

### PoC: grant your user account direct invoke

```sh
gcloud run services add-iam-policy-binding beacon-web \
  --region=${REGION} \
  --member="user:YOUR-EMAIL@example.com" \
  --role=roles/run.invoker \
  --project=${GCP_PROJECT_ID}
```

### Verify via curl (OIDC token)

```sh
URL=$(gcloud run services describe beacon-web --region=${REGION} --format='value(status.url)' --project=${GCP_PROJECT_ID})
curl -sL -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -w "\nHTTP=%{http_code}\n" \
  ${URL}/dashboard | head -10
```

Expected: `HTTP=200` and HTML containing `<title>BEACON — Dashboard</title>`.

### Browser access (PoC quick path)

```sh
gcloud run services proxy beacon-web --region=${REGION} --project=${GCP_PROJECT_ID}
```

Then open `http://localhost:8080/dashboard` in a browser. The proxy injects the developer's identity token automatically.

### Production: IAP / Internal Load Balancer

For production, place the Service behind an Internal Load Balancer and enable Cloud IAP so the endpoint is restricted to org users without exposing a public URL. This requires VPC and IAP configuration outside Cloud Run; see [GCP IAP documentation](https://cloud.google.com/iap/docs).
