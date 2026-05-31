# BEACON — Cloud Run デプロイ

英語版（正本）: [`docs/deploy.md`](deploy.md)

デプロイ前に [docs/setup.ja.md](setup.ja.md) の環境構築を完了させること。Threats タブを利用する場合は、先に SAGE Analysis API (`sage-api`) をデプロイすること — [SAGE deploy.md](../../sage/docs/deploy.md) Step 10 を参照。

---

## Step 1 — BEACON Web ダッシュボードを Cloud Run にデプロイ

BEACON の Web UI をコンテナイメージとしてビルドし、Cloud Run Service としてデプロイする。

```sh
# .env が未読み込みの場合はロード
source .env
export REGION=${VERTEX_LOCATION:-us-central1}

# (任意) sage-api がすでにデプロイされている場合は URL を取得
export SAGE_API_URL=$(gcloud run services describe sage-api \
  --region=${REGION} --format='value(status.url)' --project=${GCP_PROJECT_ID} 2>/dev/null || echo "")

# Artifact Registry リポジトリを作成（初回のみ）
gcloud artifacts repositories create cloud-run \
  --repository-format=docker \
  --location=${REGION} \
  --project=${GCP_PROJECT_ID}

export IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/cloud-run/beacon-web

# コンテナイメージをビルドしてプッシュ
gcloud builds submit --tag ${IMAGE} --project=${GCP_PROJECT_ID}

# Cloud Run Service としてデプロイ
gcloud run deploy beacon-web \
  --image=${IMAGE} \
  --region=${REGION} \
  --no-allow-unauthenticated \
  --port=8000 \
  --service-account="beacon-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},VERTEX_LOCATION=${REGION},BEACON_STORAGE=gcs,BEACON_GCS_BUCKET=${BEACON_GCS_BUCKET},BEACON_GCS_PREFIX=prod/${SAGE_API_URL:+,SAGE_API_URL=${SAGE_API_URL}}" \
  --project=${GCP_PROJECT_ID}
```

> **`--set-env-vars` vs `--update-env-vars`:** `gcloud run services update --set-env-vars=...` を後から実行すると、env-var セット全体が**置き換え**られ、再指定しなかったキーは無音で削除される。マージするには `--update-env-vars=KEY=VAL` を使うこと。毎回の更新後に `gcloud run services describe beacon-web --format="value(spec.template.spec.containers[0].env[].name)"` で確認すること。

> **サービスアカウント:** デプロイ前に専用の `beacon-sa` サービスアカウントを作成し、`roles/aiplatform.user`（Vertex AI Gemini）、`roles/storage.objectAdmin`（GCS 成果物）、`roles/run.invoker`（Cloud Scheduler または BEACON-to-SAGE 認証用）を付与すること。
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

> **Secret Manager（任意）:** 本番環境では `BEACON_GCS_PREFIX` などの機密値を Secret Manager に格納し、`--set-env-vars` の代わりに `--set-secrets="BEACON_GCS_PREFIX=beacon-gcs-prefix:latest"` で参照することを推奨する。上記の例は PoC の簡略化として env-var を直接使用している。

> **SAGE Analysis API への接続:** BEACON の初回デプロイ時に `sage-api` がまだデプロイされていない場合は、後からマージ形式の update で `SAGE_API_URL` を追加する:
> ```sh
> gcloud run services update beacon-web \
>   --region=${REGION} \
>   --update-env-vars="SAGE_API_URL=$(gcloud run services describe sage-api --region=${REGION} --format='value(status.url)' --project=${GCP_PROJECT_ID})" \
>   --project=${GCP_PROJECT_ID}
> ```

---

## Step 2 — アクセス付与と動作確認

サービスは `--no-allow-unauthenticated` でデプロイされるため、初回アクセスには IAM バインディングが必要である。

### PoC: ユーザーアカウントに invoker を直接付与

```sh
gcloud run services add-iam-policy-binding beacon-web \
  --region=${REGION} \
  --member="user:YOUR-EMAIL@example.com" \
  --role=roles/run.invoker \
  --project=${GCP_PROJECT_ID}
```

### curl による動作確認（OIDC トークン使用）

```sh
URL=$(gcloud run services describe beacon-web --region=${REGION} --format='value(status.url)' --project=${GCP_PROJECT_ID})
curl -sL -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -w "\nHTTP=%{http_code}\n" \
  ${URL}/dashboard | head -10
```

期待結果: `HTTP=200` かつ `<title>BEACON — Dashboard</title>` を含む HTML。

### ブラウザアクセス（PoC 簡易確認）

```sh
gcloud run services proxy beacon-web --region=${REGION} --project=${GCP_PROJECT_ID}
```

ブラウザで `http://localhost:8080/dashboard` を開く。proxy が開発者の identity token を自動注入する。

### 本番環境: IAP / 内部ロードバランサ

本番環境では、Service を内部ロードバランサの背後に配置し Cloud IAP を有効にすることで、パブリック URL を公開せずに組織ユーザーのみにアクセスを制限する。これには Cloud Run 外部の VPC および IAP 設定が必要である。詳細は [GCP IAP ドキュメント](https://cloud.google.com/iap/docs) を参照。
