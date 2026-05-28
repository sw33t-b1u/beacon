# BEACON — Cloud Run デプロイ

英語版（正本）: [`docs/deploy.md`](deploy.md)

デプロイ前に [docs/setup.ja.md](setup.ja.md) の環境構築を完了させること。

---

## Web ダッシュボードを Cloud Run にデプロイ

コンテナイメージをビルドし、BEACON の Web UI を IAP 保護付き Cloud Run サービスとしてデプロイする。

```sh
# .env が未読み込みの場合はロード
source .env
export REGION=${VERTEX_LOCATION:-us-central1}

# Artifact Registry リポジトリを作成（初回のみ）
gcloud artifacts repositories create cloud-run \
  --repository-format=docker \
  --location=${REGION} \
  --project=${GCP_PROJECT_ID}

export IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/cloud-run/beacon-web

# Cloud Build でコンテナイメージをビルドしてプッシュ
gcloud builds submit --tag ${IMAGE} --project=${GCP_PROJECT_ID}

# Cloud Run サービスとしてデプロイ（常時起動、パブリックアクセスなし）
gcloud run deploy beacon-web \
  --image=${IMAGE} \
  --region=${VERTEX_LOCATION:-us-central1} \
  --no-allow-unauthenticated \
  --port=8000 \
  --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},VERTEX_LOCATION=${VERTEX_LOCATION:-us-central1},BEACON_STORAGE=${BEACON_STORAGE:-gcs},BEACON_GCS_BUCKET=${BEACON_GCS_BUCKET},SAGE_API_URL=${SAGE_API_URL}" \
  --set-secrets="BEACON_GCS_PREFIX=beacon-gcs-prefix:latest" \
  --project=${GCP_PROJECT_ID}
```

> **Secret Manager:** 機密値は
> `gcloud secrets create beacon-gcs-prefix --data-file=- <<< "prod/"` で登録し、
> `--set-env-vars` の代わりに `--set-secrets` で参照する。

> **サービスアカウント:** デプロイ前に専用サービスアカウントを作成し、
> `roles/aiplatform.user`（Vertex AI Gemini）、`roles/storage.objectAdmin`
>（GCS 成果物）、`roles/run.invoker` を付与すること。
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

> **IAP 保護:** Cloud Run サービスで Identity-Aware Proxy を有効にし、
> 認可済みユーザーのみにアクセスを制限する。サービスは `--no-allow-unauthenticated`
> でデプロイされる。パブリック IP を使わない VPC 内部アクセスには
> Cloud IAP + Internal Load Balancer を組み合わせること。
