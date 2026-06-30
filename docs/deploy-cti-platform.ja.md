# CTI Platform — 統合 Cloud Run デプロイ

English version: [`docs/deploy-cti-platform.md`](deploy-cti-platform.md)

この runbook は、BEACON / TRACE / SAGE の 3 つの deploy guide を行き来せず、ブラウザ完結の
CTI workflow を立てるための推奨手順です。最小構成は次のとおりです。

| コンポーネント | Cloud Run 種別 | 用途 |
|---------------|----------------|------|
| `cti-console` | service | `/app/trace` に TRACE を同梱した BEACON web UI（`TRACE_ROOT_PATH=/app/trace`） |
| `sage-api` | service | Threats / STIX 抽出 flow が利用する読み取り専用 SAGE Analysis API |
| `sage-etl` | job | 共有 GCS storage に `db/sage.db` を publish する単一 writer ETL |
| `trace-crawl` | job（任意） | ブラウザ外でのスケジュール / バックグラウンド TRACE 収集 |

SAGE は意図的に console image へ同梱しません。console は HTTP 経由で `sage-api` を呼び、
グラフ DB を書くのは `sage-etl` だけです。これによりブラウザ操作と graph write を分離します。

---

## Storage contract

BEACON / TRACE / SAGE で 1 つの共有 bucket と prefix を使います。

```text
gs://${STORAGE_BUCKET}/${STORAGE_PREFIX}pir/      # sage-etl へ渡す reviewed PIR
gs://${STORAGE_BUCKET}/${STORAGE_PREFIX}assets/   # BEACON asset artifacts
gs://${STORAGE_BUCKET}/${STORAGE_PREFIX}stix/     # TRACE STIX bundles
gs://${STORAGE_BUCKET}/${STORAGE_PREFIX}db/       # SAGE SQLite database (db/sage.db)
```

`STORAGE_PREFIX` は空でも有効です。その場合は bucket root の `pir/`、`assets/`、`stix/`、`db/`
を使います。`sage-etl` には、検証済み PIR を次の安定パスへ配置してから実行します。

```text
gs://${PIR_GCS_BUCKET}/${PIR_ONLY_DIR}/pir.json
```

統合 config の既定では、`PIR_GCS_BUCKET=${STORAGE_BUCKET}`、
`PIR_ONLY_DIR=${STORAGE_PREFIX}pir` です。

---

## 前提条件

- `gcloud` がインストール済みで認証済みであること。
- 対象 project で Cloud Run service/job、IAM binding、Artifact Registry、Cloud Build、GCS bucket を作成・変更できる権限があること。
- script 既定値を使う場合、`beacon/`、`sage/`、`trace/` が sibling checkout であること。配置が違う場合は `SAGE_REPO` / `TRACE_REPO` を上書きします。
- 本番再現性のため、検証済みの `TRACE_REF`（tag または commit）を選ぶこと。cti-console image は Collection tab 用に
  `discover-pir`、`input/source_catalog.example.yaml`、GCS-native input resolution を同梱するため、TRACE 3.2.0 以降が必要です。
  `TRACE_REF=main` のままだと最新 TRACE を追従し、BEACON/TRACE の PIR-STIX contract drift を招く可能性があります。

orchestration script は実際の `gcloud` を実行します。まず `--dry-run` で確認してください。

---

## 単一 config block

version control 外のローカル config 例（`/tmp/cti-platform.env`）:

```bash
GCP_PROJECT_ID="your-project-id"
REGION="us-central1"

# BEACON / TRACE / SAGE が共有する artifact location。
STORAGE_BUCKET="your-cti-platform-bucket"
STORAGE_PREFIX="prod/"        # 空も有効。非空なら末尾 slash を維持する。

# 再現可能な cti-console build。TRACE >= 3.2.0 が必要。
TRACE_REF="v3.2.0"

# repo が beacon/ の sibling でない場合のみ指定。
# SAGE_REPO="../sage"
# TRACE_REPO="../trace"

# 任意の service account / Artifact Registry 名。
# BEACON_SA="beacon-sa"
# SAGE_SA="sage-etl"
# TRACE_SA="trace-crawl"
# AR_REPO="cloud-run"
```

---

## 推奨手順: runbook + script

BEACON repository root から実行します。

```bash
# 実行される gcloud command を確認する。
./scripts/deploy-cti-platform.sh --config /tmp/cti-platform.env --dry-run

# 最小 platform を deploy: setup -> sage-api -> cti-console -> invoker -> sage-etl。
./scripts/deploy-cti-platform.sh --config /tmp/cti-platform.env

# 任意: standalone の scheduled/background TRACE job も含める。
./scripts/deploy-cti-platform.sh --config /tmp/cti-platform.env --with-trace-crawl
```

script は Cloud Run が許す範囲で idempotent です。service account、Artifact Registry repository、
bucket、job は存在確認してから作成します。service deploy は新 revision を作ります。IAM binding は再実行可能です。

個別 step だけの実行もできます。

```bash
./scripts/deploy-cti-platform.sh --config /tmp/cti-platform.env setup
./scripts/deploy-cti-platform.sh --config /tmp/cti-platform.env sage-api
./scripts/deploy-cti-platform.sh --config /tmp/cti-platform.env cti-console invoker
./scripts/deploy-cti-platform.sh --config /tmp/cti-platform.env sage-etl
```

---

## script が行うこと

1. Cloud Run、Artifact Registry、Cloud Build、Vertex AI、Cloud Scheduler API を有効化する。
2. 必要なら `cloud-run` Artifact Registry repository を作成する。
3. service account を作成する。
   - `beacon-sa`: `cti-console` 用。
   - `sage-etl`: `sage-api` と `sage-etl` 用。
   - `trace-crawl`: 任意の TRACE job 用。
4. 現行 deployment model に必要な role を付与する。
5. 共有 GCS bucket を作成する。
6. 先に `sage-api` を build/deploy し、URL を確保する。
7. 次の設定で `cti-console` を build/deploy する。
   - `TRACE_ROOT_PATH=/app/trace`
   - `SAGE_API_URL=<sage-api URL>`
   - `BEACON_STORAGE=gcs`
   - `TRACE_STORAGE=gcs`
   - 共有 bucket/prefix 設定
8. `beacon-sa` に `sage-api` の `roles/run.invoker` を付与する。
9. `${PIR_ONLY_DIR}/pir.json` を `/config/pir.json` として見せる GCS volume 付きで `sage-etl` を作成または更新する。
10. 任意で `trace-crawl` を作成または更新する。

---

## ETL 実行前の analyst handoff

infrastructure は PIR data が無くても deploy できます。`sage-etl` 実行前に content flow を完了してください。

1. console を開く。

   ```bash
   gcloud run services proxy cti-console --region=${REGION} --project=${GCP_PROJECT_ID}
   # http://localhost:8080/dashboard を開く
   ```

2. UI で PIR と assets を draft / review する。統合 env vars により、artifact は共有 GCS bucket/prefix に保存されます。
3. Collection タブから TRACE 収集を実行する。統合 GCS config では、console は
   `${STORAGE_PREFIX}pir/pir_output_<timestamp>.json` のような storage key を
   TRACE に渡し、TRACE は `TRACE_STORAGE=gcs` 経由で PIR / catalog 入力を解決する。
   あるいは `sources.yaml` を `gs://${STORAGE_BUCKET}/input/sources.yaml` に upload して、
   任意の `trace-crawl` job を使います。
4. graph ingest 前に TRACE で PIR / assets / STIX を検証する。artifact path は運用により異なるため、詳細な command は standalone TRACE usage guide を参照してください。
5. reviewed/validated PIR を ETL 用の安定パスに promote する。

   ```bash
   gcloud storage cp ./pir_output.json gs://${STORAGE_BUCKET}/${STORAGE_PREFIX}pir/pir.json
   ```

6. ETL を実行する。

   ```bash
   gcloud run jobs execute sage-etl --region=${REGION} --project=${GCP_PROJECT_ID}
   ```

`sage-api` は cold start 時に `db/sage.db` を読みます。ETL 成功後、scale-to-zero により次回 request で自然に refresh されます。強制 refresh したい場合は `sage-api` の新 revision を deploy してください。

---

## 動作確認

```bash
# SAGE API liveness（auth + service startup。graph data は不要）。
URL=$(gcloud run services describe sage-api \
  --region=${REGION} --format='value(status.url)' --project=${GCP_PROJECT_ID})

curl -sL -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -w "\nHTTP=%{http_code}\n" ${URL}/openapi.json | head -5

# console は local proxy で開く。
gcloud run services proxy cti-console --region=${REGION} --project=${GCP_PROJECT_ID}
# http://localhost:8080/dashboard を開く
```

期待値: `sage-api` が `HTTP=200` と `"title":"SAGE Analysis API"` を含む JSON を返す。
console は dashboard を表示し、image 内で `TRACE_ROOT_PATH=/app/trace` が設定されているため Collection は TRACE を見つけられる。

---

## standalone deploy guide を使う場合

次のような非標準 topology では、各 repo の deploy guide を使ってください。

- ブラウザから TRACE を実行しない BEACON-only `beacon-web`。
- source mount などを独自化した TRACE-only schedule pipeline。
- SAGE Spanner backend（`SAGE_DB=spanner`）。
- custom IAM、IAP、内部ロードバランサ、VPC Service Controls、custom domain。

それ以外では、この統合 CTI Platform runbook を推奨します。
