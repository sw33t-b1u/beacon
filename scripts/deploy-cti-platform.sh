#!/usr/bin/env bash
# deploy-cti-platform.sh — idempotent orchestration for the CTI Platform.
#
# Stands up the minimal platform on Cloud Run, in dependency order:
#   1. Common Day-0 setup (APIs, Artifact Registry, service accounts, IAM, GCS)
#   2. sage-api          (Cloud Run service, read-only Analysis API)
#   3. cti-console       (Cloud Run service, BEACON web + bundled TRACE)
#   4. grant beacon-sa roles/run.invoker on sage-api
#   5. sage-etl          (Cloud Run job, single writer)
#   6. trace-crawl       (Cloud Run job, optional scheduled collection)
#
# This script only runs `gcloud`/`gcloud builds`; it makes no source changes.
# It is the executable form of docs/deploy-cti-platform.md — read that runbook
# for the conceptual flow, IAM rationale, and the analyst PIR/validate steps
# that sit between cti-console and sage-etl.
#
# Usage:
#   ./scripts/deploy-cti-platform.sh [--config FILE] [--dry-run] [--with-trace-crawl] [STEP...]
#
#   --config FILE        Source FILE for configuration before running (optional;
#                        otherwise configuration comes from the environment).
#   --dry-run            Print every gcloud command instead of executing it.
#   --with-trace-crawl   Also deploy the optional trace-crawl Cloud Run job.
#   STEP...              One or more of: setup sage-api cti-console invoker
#                        sage-etl trace-crawl. Default: all except trace-crawl
#                        (add --with-trace-crawl to include it).
#
# Required configuration (environment variables or --config file):
#   GCP_PROJECT_ID       Target GCP project id.
#   STORAGE_BUCKET       Shared GCS bucket for BEACON/TRACE/SAGE artifacts.
#
# Optional configuration (defaults shown):
#   REGION=us-central1               Cloud Run / Artifact Registry / bucket region.
#   STORAGE_PREFIX=                  Shared key prefix; empty writes to bucket root
#                                    (pir/, assets/, stix/, db/).
#   PIR_GCS_BUCKET=$STORAGE_BUCKET   Bucket sage-etl mounts pir.json from.
#   PIR_ONLY_DIR=${STORAGE_PREFIX}pir
#                                    Sub-dir mounted at /config for pir.json.
#   TRACE_REF=<tag-or-commit>        TRACE git ref baked into the cti-console image.
#                                    Required for cti-console; pin a tested tag or
#                                    commit to avoid PIR/STIX drift.
#   SAGE_REPO=<beacon>/../sage       Path to the SAGE repo checkout (for its build).
#   TRACE_REPO=<beacon>/../trace     Path to the TRACE repo checkout (trace-crawl).
#   BEACON_SA=beacon-sa              BEACON/console runtime service account name.
#   SAGE_SA=sage-etl                 SAGE api+etl runtime service account name.
#   TRACE_SA=trace-crawl             TRACE crawl runtime service account name.
#   AR_REPO=cloud-run                Artifact Registry docker repository name.
#
# Real `gcloud` execution requires GCP credentials and network. Run it yourself;
# the agent never executes this script. push/tag/release remain user-handoff.

set -euo pipefail

# --- Resolve repo locations -------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BEACON_REPO="$(cd "${SCRIPT_DIR}/.." && pwd)"

# --- Parse arguments --------------------------------------------------------
DRY_RUN=0
WITH_TRACE_CRAWL=0
CONFIG_FILE=""
STEPS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG_FILE="${2:?--config needs a file}"; shift 2 ;;
    --config=*) CONFIG_FILE="${1#*=}"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --with-trace-crawl) WITH_TRACE_CRAWL=1; shift ;;
    -h|--help) sed -n '2,48p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    setup|sage-api|cti-console|invoker|sage-etl|trace-crawl) STEPS+=("$1"); shift ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -n "${CONFIG_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
fi

# --- Configuration defaults -------------------------------------------------
GCP_PROJECT_ID="${GCP_PROJECT_ID:-}"
STORAGE_BUCKET="${STORAGE_BUCKET:-}"
REGION="${REGION:-us-central1}"
STORAGE_PREFIX="${STORAGE_PREFIX:-}"
PIR_GCS_BUCKET="${PIR_GCS_BUCKET:-${STORAGE_BUCKET}}"
PIR_ONLY_DIR="${PIR_ONLY_DIR:-${STORAGE_PREFIX}pir}"
TRACE_REF="${TRACE_REF:-}"
SAGE_REPO="${SAGE_REPO:-${BEACON_REPO}/../sage}"
TRACE_REPO="${TRACE_REPO:-${BEACON_REPO}/../trace}"
BEACON_SA="${BEACON_SA:-beacon-sa}"
SAGE_SA="${SAGE_SA:-sage-etl}"
TRACE_SA="${TRACE_SA:-trace-crawl}"
AR_REPO="${AR_REPO:-cloud-run}"

# --- Helpers ----------------------------------------------------------------
log()  { printf '\n=== %s ===\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

run() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '+'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "ERROR: required configuration '${name}' is empty (set it via env or --config)." >&2
    exit 1
  fi
}

# Run a gcloud "describe" probe; treat any failure as "does not exist".
# In --dry-run we report "absent" so the create path prints its commands.
exists() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    return 1
  fi
  "$@" >/dev/null 2>&1
}

sa_email() { printf '%s@%s.iam.gserviceaccount.com' "$1" "${GCP_PROJECT_ID}"; }

image_uri() {
  printf '%s-docker.pkg.dev/%s/%s/%s' "${REGION}" "${GCP_PROJECT_ID}" "${AR_REPO}" "$1"
}

ensure_sa() {
  local name="$1" display="$2"
  if exists gcloud iam service-accounts describe "$(sa_email "${name}")" --project="${GCP_PROJECT_ID}"; then
    echo "service account ${name} already exists"
  else
    run gcloud iam service-accounts create "${name}" \
      --display-name="${display}" --project="${GCP_PROJECT_ID}"
  fi
}

grant_project_role() {
  local member="$1" role="$2"
  run gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
    --member="${member}" --role="${role}" --condition=None --quiet
}

grant_bucket_role() {
  local bucket="$1" member="$2" role="$3"
  run gcloud storage buckets add-iam-policy-binding "gs://${bucket}" \
    --member="${member}" --role="${role}"
}

ensure_bucket() {
  local bucket="$1"
  if exists gcloud storage buckets describe "gs://${bucket}"; then
    echo "bucket gs://${bucket} already exists"
  else
    run gcloud storage buckets create "gs://${bucket}" \
      --location="${REGION}" --project="${GCP_PROJECT_ID}"
  fi
}

# --- Steps ------------------------------------------------------------------
step_setup() {
  log "Day-0 common setup"
  require_var GCP_PROJECT_ID
  require_var STORAGE_BUCKET

  log "Enable APIs"
  run gcloud services enable \
    run.googleapis.com artifactregistry.googleapis.com \
    cloudbuild.googleapis.com aiplatform.googleapis.com \
    cloudscheduler.googleapis.com --project="${GCP_PROJECT_ID}"

  log "Artifact Registry repository: ${AR_REPO}"
  if exists gcloud artifacts repositories describe "${AR_REPO}" \
      --location="${REGION}" --project="${GCP_PROJECT_ID}"; then
    echo "repository ${AR_REPO} already exists"
  else
    run gcloud artifacts repositories create "${AR_REPO}" \
      --repository-format=docker --location="${REGION}" --project="${GCP_PROJECT_ID}"
  fi

  log "Service accounts"
  ensure_sa "${BEACON_SA}" "BEACON / CTI console"
  ensure_sa "${SAGE_SA}" "SAGE API + ETL"
  ensure_sa "${TRACE_SA}" "TRACE Crawl Job"

  log "Project-level IAM"
  local beacon_m sage_m trace_m
  beacon_m="serviceAccount:$(sa_email "${BEACON_SA}")"
  sage_m="serviceAccount:$(sa_email "${SAGE_SA}")"
  trace_m="serviceAccount:$(sa_email "${TRACE_SA}")"
  for role in roles/aiplatform.user roles/storage.objectAdmin roles/run.invoker; do
    grant_project_role "${beacon_m}" "${role}"
  done
  for role in roles/storage.objectViewer roles/run.invoker; do
    grant_project_role "${sage_m}" "${role}"
  done
  for role in roles/aiplatform.user roles/storage.objectAdmin roles/run.invoker; do
    grant_project_role "${trace_m}" "${role}"
  done

  log "GCS buckets"
  ensure_bucket "${STORAGE_BUCKET}"
  if [[ "${PIR_GCS_BUCKET}" != "${STORAGE_BUCKET}" ]]; then
    ensure_bucket "${PIR_GCS_BUCKET}"
  fi

  log "Bucket-level IAM (single-writer sage-etl needs write on shared bucket)"
  grant_bucket_role "${STORAGE_BUCKET}" "${sage_m}" roles/storage.objectAdmin
}

sage_image() { image_uri "sage-etl"; }
trace_image() { image_uri "trace-crawl"; }
console_image() { image_uri "cti-console"; }

build_sage_image() {
  log "Build SAGE image from ${SAGE_REPO}"
  run gcloud builds submit "${SAGE_REPO}" --tag "$(sage_image)" --project="${GCP_PROJECT_ID}"
}

step_sage_api() {
  require_var GCP_PROJECT_ID
  require_var STORAGE_BUCKET
  build_sage_image
  log "Deploy sage-api (Cloud Run service)"
  run gcloud run deploy sage-api \
    --image="$(sage_image)" \
    --region="${REGION}" \
    --no-allow-unauthenticated \
    --command="uv" \
    --args="run,sage,serve-api,--host,0.0.0.0,--port,8080" \
    --port=8080 \
    --service-account="$(sa_email "${SAGE_SA}")" \
    --set-env-vars="SAGE_STORAGE=gcs,SAGE_STORAGE_BUCKET=${STORAGE_BUCKET},SAGE_STORAGE_PREFIX=${STORAGE_PREFIX}" \
    --project="${GCP_PROJECT_ID}"
}

sage_api_url() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf 'SAGE_API_URL_FROM_SAGE_API_SERVICE'
    return 0
  fi
  gcloud run services describe sage-api \
    --region="${REGION}" --format='value(status.url)' \
    --project="${GCP_PROJECT_ID}" 2>/dev/null || echo ""
}

step_cti_console() {
  require_var GCP_PROJECT_ID
  require_var STORAGE_BUCKET
  require_var TRACE_REF
  if [[ "${TRACE_REF}" == "main" ]]; then
    warn "TRACE_REF=main: image tracks latest TRACE. Pin a tested tag or commit for reproducible production builds."
  fi

  log "Build cti-console image (BEACON web + TRACE@${TRACE_REF})"
  run gcloud builds submit "${BEACON_REPO}" \
    --config="${BEACON_REPO}/cloudbuild.cti-console.yaml" \
    --substitutions="_IMAGE=$(console_image),_TRACE_REF=${TRACE_REF}" \
    --project="${GCP_PROJECT_ID}"

  local url
  url="$(sage_api_url)"
  if [[ -z "${url}" ]]; then
    warn "sage-api URL not found; deploying cti-console without SAGE_API_URL (wire it later with --update-env-vars)."
  fi

  log "Deploy cti-console (Cloud Run service)"
  run gcloud run deploy cti-console \
    --image="$(console_image)" \
    --region="${REGION}" \
    --no-allow-unauthenticated \
    --port=8000 \
    --service-account="$(sa_email "${BEACON_SA}")" \
    --set-env-vars="TRACE_ROOT_PATH=/app/trace,SAGE_API_URL=${url},BEACON_STORAGE=gcs,BEACON_STORAGE_BUCKET=${STORAGE_BUCKET},BEACON_STORAGE_PREFIX=${STORAGE_PREFIX},TRACE_STORAGE=gcs,TRACE_STORAGE_BUCKET=${STORAGE_BUCKET},TRACE_STORAGE_PREFIX=${STORAGE_PREFIX}" \
    --project="${GCP_PROJECT_ID}"
}

step_invoker() {
  require_var GCP_PROJECT_ID
  log "Grant beacon-sa roles/run.invoker on sage-api"
  run gcloud run services add-iam-policy-binding sage-api \
    --region="${REGION}" \
    --member="serviceAccount:$(sa_email "${BEACON_SA}")" \
    --role=roles/run.invoker \
    --project="${GCP_PROJECT_ID}"
}

step_sage_etl() {
  require_var GCP_PROJECT_ID
  require_var STORAGE_BUCKET
  build_sage_image
  local create_or_update=create
  if exists gcloud run jobs describe sage-etl --region="${REGION}" --project="${GCP_PROJECT_ID}"; then
    create_or_update=update
  fi
  log "Deploy sage-etl (Cloud Run job: ${create_or_update})"
  run gcloud run jobs "${create_or_update}" sage-etl \
    --image="$(sage_image)" \
    --region="${REGION}" \
    --service-account="$(sa_email "${SAGE_SA}")" \
    --set-env-vars="PIR_FILE_PATH=/config/pir.json,OPENCTI_URL=https://example.com,OPENCTI_TOKEN=skip,SAGE_STORAGE=gcs,SAGE_STORAGE_BUCKET=${STORAGE_BUCKET},SAGE_STORAGE_PREFIX=${STORAGE_PREFIX}" \
    --add-volume=name=pir,type=cloud-storage,bucket="${PIR_GCS_BUCKET}",mount-options="only-dir=${PIR_ONLY_DIR}" \
    --add-volume-mount=volume=pir,mount-path=/config \
    --project="${GCP_PROJECT_ID}"
  echo "Reminder: a validated pir.json must exist at gs://${PIR_GCS_BUCKET}/${PIR_ONLY_DIR}/pir.json before executing the job."
  echo "Execute with: gcloud run jobs execute sage-etl --region=${REGION} --project=${GCP_PROJECT_ID}"
}

step_trace_crawl() {
  require_var GCP_PROJECT_ID
  require_var STORAGE_BUCKET
  log "Build TRACE image from ${TRACE_REPO}"
  run gcloud builds submit "${TRACE_REPO}" --tag "$(trace_image)" --project="${GCP_PROJECT_ID}"
  local create_or_update=create
  if exists gcloud run jobs describe trace-crawl --region="${REGION}" --project="${GCP_PROJECT_ID}"; then
    create_or_update=update
  fi
  log "Deploy trace-crawl (Cloud Run job: ${create_or_update})"
  run gcloud run jobs "${create_or_update}" trace-crawl \
    --image="$(trace_image)" \
    --region="${REGION}" \
    --service-account="$(sa_email "${TRACE_SA}")" \
    --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},VERTEX_LOCATION=${REGION},TRACE_STORAGE=gcs,TRACE_STORAGE_BUCKET=${STORAGE_BUCKET},TRACE_STORAGE_PREFIX=${STORAGE_PREFIX}" \
    --add-volume=name=sources,type=cloud-storage,bucket="${STORAGE_BUCKET}",mount-options="only-dir=input" \
    --add-volume-mount=volume=sources,mount-path=/app/input \
    --project="${GCP_PROJECT_ID}"
  echo "Reminder: upload sources.yaml to gs://${STORAGE_BUCKET}/input/sources.yaml before executing the job."
}

# --- Main -------------------------------------------------------------------
if [[ ${#STEPS[@]} -eq 0 ]]; then
  STEPS=(setup sage-api cti-console invoker sage-etl)
  if [[ "${WITH_TRACE_CRAWL}" -eq 1 ]]; then
    STEPS+=(trace-crawl)
  fi
fi

[[ "${DRY_RUN}" -eq 1 ]] && log "DRY RUN — printing commands only"

for step in "${STEPS[@]}"; do
  case "${step}" in
    setup) step_setup ;;
    sage-api) step_sage_api ;;
    cti-console) step_cti_console ;;
    invoker) step_invoker ;;
    sage-etl) step_sage_etl ;;
    trace-crawl) step_trace_crawl ;;
    *) echo "ERROR: unknown step: ${step}" >&2; exit 2 ;;
  esac
done

log "Done"
