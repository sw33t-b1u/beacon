# BEACON — Cloud Run Deployment

Japanese translation: [`docs/deploy.ja.md`](deploy.ja.md)

Before deploying, complete the environment setup described in [docs/setup.md](setup.md).

---

## Deploy Web Dashboard to Cloud Run

Build the container image and deploy the BEACON web UI as a Cloud Run Service with IAP protection.

```sh
# Load .env if not already sourced
source .env
export REGION=${VERTEX_LOCATION:-us-central1}

# Create Artifact Registry repository (first time only)
gcloud artifacts repositories create cloud-run \
  --repository-format=docker \
  --location=${REGION} \
  --project=${GCP_PROJECT_ID}

export IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/cloud-run/beacon-web

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
