# CTI Platform — Unified Cloud Run Deployment

Japanese translation: [`docs/deploy-cti-platform.ja.md`](deploy-cti-platform.ja.md)

This runbook is the recommended path when you want a browser-complete CTI
workflow without hopping between the BEACON, TRACE, and SAGE deploy guides. It
deploys the minimal platform:

| Component | Cloud Run type | Purpose |
|-----------|----------------|---------|
| `cti-console` | service | BEACON web UI with TRACE bundled at `/app/trace` (`TRACE_ROOT_PATH=/app/trace`) |
| `sage-api` | service | Read-only SAGE Analysis API used by the Threats and STIX extraction flows |
| `sage-etl` | job | Single-writer ETL that publishes `db/sage.db` to shared GCS storage |
| `trace-crawl` | job (optional) | Scheduled/background TRACE collection outside the browser console |

SAGE is intentionally **not** baked into the console image. The console calls
`sage-api` over HTTP, and only `sage-etl` writes the graph database. This keeps
browser operations and graph writes separate.

---

## Storage contract

Use one shared bucket and one shared prefix for BEACON, TRACE, and SAGE:

```text
gs://${STORAGE_BUCKET}/${STORAGE_PREFIX}pir/      # reviewed PIR handoff for sage-etl
gs://${STORAGE_BUCKET}/${STORAGE_PREFIX}assets/   # BEACON asset artifacts
gs://${STORAGE_BUCKET}/${STORAGE_PREFIX}stix/     # TRACE STIX bundles
gs://${STORAGE_BUCKET}/${STORAGE_PREFIX}db/       # SAGE SQLite database (db/sage.db)
```

`STORAGE_PREFIX` may be empty; then the platform writes directly to `pir/`,
`assets/`, `stix/`, and `db/` at the bucket root. For `sage-etl`, the validated
PIR must be promoted to:

```text
gs://${PIR_GCS_BUCKET}/${PIR_ONLY_DIR}/pir.json
```

With the default unified config, `PIR_GCS_BUCKET=${STORAGE_BUCKET}` and
`PIR_ONLY_DIR=${STORAGE_PREFIX}pir`.

---

## Prerequisites

- `gcloud` installed and authenticated.
- The caller can create/modify Cloud Run services/jobs, IAM bindings, Artifact
  Registry repositories, Cloud Build builds, and GCS buckets in the target
  project.
- Local sibling checkouts of `beacon/`, `sage/`, and `trace/` when using the
  script defaults. Override `SAGE_REPO` / `TRACE_REPO` if your layout differs.
- Choose a tested `TRACE_REF` (tag or commit) for reproducible production
  builds. The cti-console image requires TRACE 3.2.0 or later because it bundles
  `discover-pir`, `input/source_catalog.example.yaml`, and GCS-native input
  resolution for the Collection tab.
  Leaving `TRACE_REF=main` tracks the latest TRACE and can introduce
  BEACON/TRACE PIR-STIX contract drift.

The orchestration script runs real `gcloud` commands. Use `--dry-run` first.

---

## One configuration block

Create a local config file outside version control, for example
`/tmp/cti-platform.env`:

```bash
GCP_PROJECT_ID="your-project-id"
REGION="us-central1"

# Shared artifact location used by BEACON, TRACE, and SAGE.
STORAGE_BUCKET="your-cti-platform-bucket"
STORAGE_PREFIX="prod/"        # Empty is valid; keep the trailing slash if non-empty.

# Reproducible cti-console build. Requires TRACE >= 3.2.0.
TRACE_REF="v3.2.0"

# Optional if the repos are not siblings of beacon/.
# SAGE_REPO="../sage"
# TRACE_REPO="../trace"

# Optional service-account / Artifact Registry names.
# BEACON_SA="beacon-sa"
# SAGE_SA="sage-etl"
# TRACE_SA="trace-crawl"
# AR_REPO="cloud-run"
```

---

## Recommended path: runbook + script

From the BEACON repository root:

```bash
# Preview the exact gcloud commands.
./scripts/deploy-cti-platform.sh --config /tmp/cti-platform.env --dry-run

# Deploy the minimal platform: setup -> sage-api -> cti-console -> invoker -> sage-etl.
./scripts/deploy-cti-platform.sh --config /tmp/cti-platform.env

# Optional: include the standalone scheduled/background TRACE job.
./scripts/deploy-cti-platform.sh --config /tmp/cti-platform.env --with-trace-crawl
```

The script is idempotent where Cloud Run supports it: it checks before creating
service accounts, Artifact Registry repositories, buckets, and jobs. Service
deploys create a new revision. IAM bindings are safe to re-run.

You can also run individual steps:

```bash
./scripts/deploy-cti-platform.sh --config /tmp/cti-platform.env setup
./scripts/deploy-cti-platform.sh --config /tmp/cti-platform.env sage-api
./scripts/deploy-cti-platform.sh --config /tmp/cti-platform.env cti-console invoker
./scripts/deploy-cti-platform.sh --config /tmp/cti-platform.env sage-etl
```

---

## What the script does

1. Enables the required APIs: Cloud Run, Artifact Registry, Cloud Build, Vertex
   AI, and Cloud Scheduler.
2. Creates the `cloud-run` Artifact Registry repository if needed.
3. Creates service accounts:
   - `beacon-sa` for `cti-console`.
   - `sage-etl` for `sage-api` and `sage-etl`.
   - `trace-crawl` for the optional TRACE job.
4. Grants the roles required by the current deployment model.
5. Creates the shared GCS bucket.
6. Builds and deploys `sage-api` first, so its URL exists.
7. Builds and deploys `cti-console` with:
   - `TRACE_ROOT_PATH=/app/trace`
   - `SAGE_API_URL=<sage-api URL>`
   - `BEACON_STORAGE=gcs`
   - `TRACE_STORAGE=gcs`
   - shared bucket/prefix settings
8. Grants `beacon-sa` `roles/run.invoker` on `sage-api`.
9. Creates or updates `sage-etl` with a GCS volume that exposes
   `${PIR_ONLY_DIR}/pir.json` as `/config/pir.json`.
10. Optionally creates or updates `trace-crawl`.

---

## Analyst handoff before running ETL

The infrastructure can be deployed before PIR data exists. Before executing
`sage-etl`, complete the content flow:

1. Open the console:

   ```bash
   gcloud run services proxy cti-console --region=${REGION} --project=${GCP_PROJECT_ID}
   # Open http://localhost:8080/dashboard
   ```

2. Draft/review PIR and assets in the UI. With the unified env vars, artifacts
   are stored in the shared GCS bucket/prefix.
3. Run TRACE collection from the Collection tab. In the unified GCS
   configuration, the console passes storage keys such as
   `${STORAGE_PREFIX}pir/pir_output_<timestamp>.json` to TRACE, and TRACE
   resolves PIR/catalog inputs through `TRACE_STORAGE=gcs`. You can also run
   the optional `trace-crawl` job after uploading `sources.yaml` to
   `gs://${STORAGE_BUCKET}/input/sources.yaml`.

   The discovery source catalog (`source_catalog.yaml`) is the operator feed
   list for `discover-pir`; it is distinct from the `sources.yaml` consumed by
   `crawl-batch`. Both live under the `input` category. Upload the catalog to:

   ```bash
   gcloud storage cp ./source_catalog.yaml \
     gs://${STORAGE_BUCKET}/${STORAGE_PREFIX}input/source_catalog.yaml
   ```

   Then set the Discovery form's "Catalog path" to a storage key such as
   `${STORAGE_PREFIX}input/source_catalog.yaml` (a bare `input/source_catalog.yaml`
   or a `gs://...` URI also resolves). Leaving it blank falls back to the
   image-bundled `input/source_catalog.example.yaml` template, which usually
   yields zero candidates until you supply a catalog matching your PIR terms.
4. Validate the PIR/assets/STIX with TRACE before graph ingestion. The exact
   validation command depends on the artifact paths you choose; the standalone
   TRACE usage guide remains the detailed reference.
5. Promote the reviewed, validated PIR to the stable ETL location:

   ```bash
   gcloud storage cp ./pir_output.json gs://${STORAGE_BUCKET}/${STORAGE_PREFIX}pir/pir.json
   ```

6. Execute ETL:

   ```bash
   gcloud run jobs execute sage-etl --region=${REGION} --project=${GCP_PROJECT_ID}
   ```

`sage-api` reads `db/sage.db` on cold start. After a successful ETL run, scale to
zero naturally refreshes the API on the next request; to force refresh, deploy a
new `sage-api` revision.

---

## Verification

```bash
# SAGE API liveness (auth + service startup; does not require graph data).
URL=$(gcloud run services describe sage-api \
  --region=${REGION} --format='value(status.url)' --project=${GCP_PROJECT_ID})

curl -sL -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -w "\nHTTP=%{http_code}\n" ${URL}/openapi.json | head -5

# Console access through local proxy.
gcloud run services proxy cti-console --region=${REGION} --project=${GCP_PROJECT_ID}
# Open http://localhost:8080/dashboard
```

Expected: `sage-api` returns `HTTP=200` and JSON with
`"title":"SAGE Analysis API"`; the console shows the dashboard and Collection
can find TRACE because `TRACE_ROOT_PATH=/app/trace` is set in the image.

---

## When to use standalone deploy guides

Use the per-repo deploy guides when you need a non-standard topology, such as:

- BEACON-only `beacon-web` without browser TRACE execution.
- A separately scheduled TRACE-only pipeline with custom source mounting.
- SAGE Spanner backend (`SAGE_DB=spanner`).
- Custom IAM, IAP, internal load balancers, VPC Service Controls, or custom
  domains.

Otherwise, prefer this unified CTI Platform runbook.
