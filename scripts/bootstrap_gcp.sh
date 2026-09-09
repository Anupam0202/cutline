#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT to the existing billing-enabled project}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
FIRESTORE_LOCATION="${FIRESTORE_LOCATION:-nam5}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-cutline-runtime}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"

command -v gcloud >/dev/null || { echo "Google Cloud CLI is required." >&2; exit 1; }
ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -n 1)"
if [[ -z "${ACTIVE_ACCOUNT}" ]]; then
  echo "No active Google Cloud account. Authenticate before running this script." >&2
  exit 1
fi

gcloud config set project "${GOOGLE_CLOUD_PROJECT}"
LIFECYCLE_STATE="$(gcloud projects describe "${GOOGLE_CLOUD_PROJECT}" --format='value(lifecycleState)')"
BILLING_ENABLED="$(gcloud billing projects describe "${GOOGLE_CLOUD_PROJECT}" --format='value(billingEnabled)')"
if [[ "${LIFECYCLE_STATE}" != "ACTIVE" || "${BILLING_ENABLED,,}" != "true" ]]; then
  echo "The selected project must be active with billing enabled." >&2
  exit 1
fi

gcloud services enable \
  aiplatform.googleapis.com \
  artifactregistry.googleapis.com \
  billingbudgets.googleapis.com \
  cloudbuild.googleapis.com \
  compute.googleapis.com \
  firestore.googleapis.com \
  iam.googleapis.com \
  logging.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com

if gcloud firestore databases describe --database='(default)' >/dev/null 2>&1; then
  FIRESTORE_TYPE="$(gcloud firestore databases describe --database='(default)' --format='value(type)')"
  FIRESTORE_ACTUAL_LOCATION="$(gcloud firestore databases describe --database='(default)' --format='value(locationId)')"
  if [[ "${FIRESTORE_TYPE}" != "FIRESTORE_NATIVE" ]]; then
    echo "The existing default database is not Firestore Native." >&2
    exit 1
  fi
  echo "Using existing Firestore Native database in ${FIRESTORE_ACTUAL_LOCATION}."
else
  gcloud firestore databases create \
    --database='(default)' \
    --location="${FIRESTORE_LOCATION}" \
    --type=firestore-native
fi

if ! gcloud iam service-accounts describe "${SERVICE_ACCOUNT}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SERVICE_ACCOUNT_NAME}" --display-name='CUTLINE runtime'
fi
for role in roles/aiplatform.user roles/datastore.user roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "${GOOGLE_CLOUD_PROJECT}" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="${role}" \
    --condition=None >/dev/null
done

if ! gcloud secrets describe cutline-session-secret >/dev/null 2>&1; then
  gcloud secrets create cutline-session-secret --replication-policy=automatic
fi
if [[ -z "$(gcloud secrets versions list cutline-session-secret --filter='state=ENABLED' --format='value(name)' --limit=1)" ]]; then
  openssl rand -base64 48 | gcloud secrets versions add cutline-session-secret --data-file=-
fi

if ! gcloud secrets describe parallel-api-key >/dev/null 2>&1; then
  gcloud secrets create parallel-api-key --replication-policy=automatic
fi
if [[ -z "$(gcloud secrets versions list parallel-api-key --filter='state=ENABLED' --format='value(name)' --limit=1)" ]]; then
  read -r -s -p 'Parallel API key: ' PARALLEL_API_KEY
  printf '\n'
  printf '%s' "${PARALLEL_API_KEY}" | gcloud secrets versions add parallel-api-key --data-file=-
  unset PARALLEL_API_KEY
fi

for secret in cutline-session-secret parallel-api-key; do
  gcloud secrets add-iam-policy-binding "${secret}" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role=roles/secretmanager.secretAccessor >/dev/null
done

gcloud firestore fields ttls update expires_at \
  --collection-group=cutline_projects \
  --enable-ttl \
  --quiet

echo "Bootstrap complete for ${ACTIVE_ACCOUNT}. Next run ./scripts/deploy_cloud_run.sh"
