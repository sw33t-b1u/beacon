# BEACON — Cloud Run デプロイガイド

英語版（正本）: [`docs/deploy.md`](deploy.md)

デプロイ前に [docs/setup.ja.md](setup.ja.md) の手順を完了すること。デプロイ前に `make check` がパスすることを確認すること。

---

## クロスリポジトリのデプロイ順序

BEACON・SAGE・TRACE はデプロイ時に循環依存を形成する: BEACON は
`SAGE_API_URL`（sage-api の URL）を必要とし、SAGE の ETL は BEACON が生成する
検証済み `pir.json` を必要とする。この順序で循環を解く — 未解決の依存は後から
`--update-env-vars` で配線するため、BEACON はまだ存在しない `sage-api` の URL を
待ってブロックすることはない。この順序は [SAGE deploy.ja.md](../../sage/docs/deploy.ja.md)
と一致しており、両リポジトリで矛盾しない。

1. **SAGE — まず `sage-api` をデプロイ**（その GCS バケットも）。API は DB が
   無くても起動するため、BEACON が必要とする前に URL が存在する。
2. **BEACON — `beacon-web` をデプロイ。** ステップ 1 の sage-api URL を
   `SAGE_API_URL` に配線し、SAGE 側で BEACON のサービスアカウント（`beacon-sa`）に
   `sage-api` の `roles/run.invoker` を付与する（[SAGE 連携](#sage-連携クロスリポジトリ)参照）。
3. **BEACON — PIR/assets を生成。** ビジネスコンテキストから `pir_output.json` と
   asset 成果物を生成する。
4. **TRACE — validate。** assets・PIR・STIX バンドルを TRACE（すべての SAGE 入力に
   対する単一の検証ゲート）に通す。コマンドは [TRACE リポジトリ](https://github.com/sw33t-b1u/trace)
   を参照（ここでは重複させない）。
5. **SAGE — 配置して ETL 実行。** 検証済み成果物を GCS に配置し `sage-etl` を実行する。

BEACON のデプロイ時に `sage-api` が未デプロイの場合は、`SAGE_API_URL` なしで
`beacon-web` をデプロイし、後から `--update-env-vars` で追加する（[`SAGE_API_URL`（任意）](#day-1-初回デプロイ)
および Day-N 再デプロイ参照）。

---

## Day-0 前提条件

### API の有効化

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

### Artifact Registry リポジトリの作成

```sh
gcloud artifacts repositories create cloud-run \
  --repository-format=docker \
  --location=${REGION} \
  --project=${GCP_PROJECT_ID}
```

### サービスアカウントの作成と IAM ロールの付与

デプロイコマンドでサービスアカウントを参照する前に、`beacon-sa` サービスアカウントを作成して必要なロールを付与しておく。

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

> **IAM ロール説明:**
> - `roles/aiplatform.user` — LLM 分析用 Vertex AI Gemini アクセス
> - `roles/storage.objectAdmin` — GCS 成果物（BEACON_STORAGE_BUCKET）の読み書き
> - `roles/run.invoker` — BEACON が OIDC 経由で SAGE Analysis API（`sage-api`）を呼び出すために必要

### GCS バケットの作成（未作成の場合）

```sh
# ストレージバックエンドバケット（BEACON_STORAGE=gcs の場合のみ）
gcloud storage buckets create gs://${BEACON_STORAGE_BUCKET} \
  --location=${REGION} \
  --project=${GCP_PROJECT_ID}
```

---

## Day-1 初回デプロイ

### beacon-web（Cloud Run Service）

```sh
source .env
export REGION=${VERTEX_LOCATION:-us-central1}

# （任意）sage-api がすでにデプロイされている場合は URL を取得
export SAGE_API_URL=$(gcloud run services describe sage-api \
  --region=${REGION} --format='value(status.url)' --project=${GCP_PROJECT_ID} 2>/dev/null || echo "")

export IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/cloud-run/beacon-web

# Cloud Build でコンテナイメージをビルドしてプッシュ
gcloud builds submit --tag ${IMAGE} --project=${GCP_PROJECT_ID}

# Cloud Run Service としてデプロイ
gcloud run deploy beacon-web \
  --image=${IMAGE} \
  --region=${REGION} \
  --no-allow-unauthenticated \
  --port=8000 \
  --service-account="beacon-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},VERTEX_LOCATION=${REGION},BEACON_STORAGE=gcs,BEACON_STORAGE_BUCKET=${BEACON_STORAGE_BUCKET},BEACON_STORAGE_PREFIX=${BEACON_STORAGE_PREFIX:-prod/}${SAGE_API_URL:+,SAGE_API_URL=${SAGE_API_URL}}" \
  --project=${GCP_PROJECT_ID}
```

> **`--set-env-vars` vs `--update-env-vars`:** 初回デプロイでは `--set-env-vars` を使って env-var セット全体を一括設定する。以降の変更は `--update-env-vars` を使うこと（Day-N 参照）。既存サービスに `--set-env-vars` を使うと **env-var セット全体が置き換わり**、再指定しなかったキーが無音で削除される。

> **`SAGE_API_URL`（任意）:** BEACON の初回デプロイ時に `sage-api` がまだデプロイされていない場合は、後から `--update-env-vars` で追加する（後述の Day-N 再デプロイを参照）。これは[クロスリポジトリのデプロイ順序](#クロスリポジトリのデプロイ順序)の「後から配線する」分岐である — 可能なら先に `sage-api` をデプロイし、できない場合は後から `SAGE_API_URL` を配線する。

---

## Day-N 再デプロイ

### コード変更のみの場合

env-var の追加・削除がなく、コンテナイメージのみ変更する場合はこのフローを使う。

```sh
export IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/cloud-run/beacon-web

# 新しいイメージをビルドしてプッシュ
gcloud builds submit --tag ${IMAGE} --project=${GCP_PROJECT_ID}

# Cloud Run Service を更新
gcloud run services update beacon-web \
  --image=${IMAGE} \
  --region=${REGION} \
  --project=${GCP_PROJECT_ID}
```

### 既存リビジョンの env-var 変更

`--update-env-vars` と `--remove-env-vars` を使うこと — **`--set-env-vars` は使わない**。`--set-env-vars` は env-var セット全体を置き換えるため、再指定しなかったキーが無音で削除される。

```sh
# 他の変数に影響せず 1 つの変数を追加・更新する
gcloud run services update beacon-web \
  --update-env-vars=NEW_VAR=value \
  --region=${REGION} \
  --project=${GCP_PROJECT_ID}

# 古い変数を削除しながら新しい変数を追加する
gcloud run services update beacon-web \
  --update-env-vars=NEW_VAR=value \
  --remove-env-vars=OLD_VAR \
  --region=${REGION} \
  --project=${GCP_PROJECT_ID}

# sage-api デプロイ後に SAGE_API_URL を追加する
gcloud run services update beacon-web \
  --update-env-vars="SAGE_API_URL=$(gcloud run services describe sage-api --region=${REGION} --format='value(status.url)' --project=${GCP_PROJECT_ID})" \
  --region=${REGION} \
  --project=${GCP_PROJECT_ID}
```

> **確認:** `gcloud run services describe beacon-web --region=${REGION} --format="value(spec.template.spec.containers[0].env[].name)" --project=${GCP_PROJECT_ID}`

---

## アクセス（本番推奨 = L2）

デプロイ時に `--no-allow-unauthenticated` が既に設定されている。アクセスが必要なアイデンティティに `roles/run.invoker` を付与する。

### 呼び出し権限の付与

```sh
# 個人ユーザー
gcloud run services add-iam-policy-binding beacon-web \
  --region=${REGION} \
  --member="user:alice@example.com" \
  --role=roles/run.invoker \
  --project=${GCP_PROJECT_ID}

# Google グループ（チーム利用に推奨）
gcloud run services add-iam-policy-binding beacon-web \
  --region=${REGION} \
  --member="group:beacon-users@example.com" \
  --role=roles/run.invoker \
  --project=${GCP_PROJECT_ID}
```

### ブラウザアクセス

```sh
gcloud run services proxy beacon-web --region=${REGION} --project=${GCP_PROJECT_ID}
# http://localhost:8080/dashboard を開く
```

proxy が開発者の identity token を自動注入するため、bearer token の管理は不要。

### curl による動作確認

```sh
URL=$(gcloud run services describe beacon-web \
  --region=${REGION} \
  --format='value(status.url)' \
  --project=${GCP_PROJECT_ID})

curl -sL -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -w "\nHTTP=%{http_code}\n" \
  ${URL}/dashboard | head -10
```

期待結果: `HTTP=200` かつ `<title>BEACON — Dashboard</title>` を含む HTML。

### SAGE 連携（クロスリポジトリ）

BEACON のサービスアカウント（`beacon-sa`）が SAGE Analysis API を呼び出すには、`sage-api` に対して `roles/run.invoker` が必要である。SAGE 側から付与する:

```sh
gcloud run services add-iam-policy-binding sage-api \
  --region=${REGION} \
  --member="serviceAccount:beacon-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role=roles/run.invoker \
  --project=${GCP_PROJECT_ID}
```

SAGE の完全なデプロイ手順は [SAGE deploy.md](../../sage/docs/deploy.md) を参照すること。

---

## 対象外

IAP / 内部ロードバランサ / VPC Service Controls はこのガイドでは設定しない。少数の Google Workspace ユーザー運用（数名程度）では、上記の L2 IAM バインディングで十分である。コンテキストアウェアアクセスやカスタムネットワーク構成が必要な場合は https://cloud.google.com/iap/docs を参照すること。
