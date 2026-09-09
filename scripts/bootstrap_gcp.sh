#!/usr/bin/env bash
set -euo pipefail
: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT to a billing-enabled project}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
FIRESTORE_LOCATION="${FIRESTORE_LOCATION:-nam5}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-cutline-runtime}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"

gcloud auth login
gcloud auth application-default login
gcloud config set project "${GOOGLE_CLOUD_PROJECT}"
gcloud services enable aiplatform.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com firestore.googleapis.com iam.googleapis.com logging.googleapis.com run.googleapis.com secretmanager.googleapis.com

if ! gcloud firestore databases describe --database='(default)' >/dev/null 2>&1; then
  gcloud firestore databases create --database='(default)' --location="${FIRESTORE_LOCATION}" --type=firestore-native
fi
if ! gcloud iam service-accounts describe "${SERVICE_ACCOUNT}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SERVICE_ACCOUNT_NAME}" --display-name='CUTLINE runtime'
fi
for role in roles/aiplatform.user roles/datastore.user roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "${GOOGLE_CLOUD_PROJECT}" --member="serviceAccount:${SERVICE_ACCOUNT}" --role="${role}" --condition=None >/dev/null
done

if ! gcloud secrets describe cutline-session-secret >/dev/null 2>&1; then
  gcloud secrets create cutline-session-secret --replication-policy=automatic
  openssl rand -base64 48 | gcloud secrets versions add cutline-session-secret --data-file=-
fi
if ! gcloud secrets describe parallel-api-key >/dev/null 2>&1; then
  gcloud secrets create parallel-api-key --replication-policy=automatic
  read -r -s -p 'Parallel API key: ' PARALLEL_API_KEY; printf '\n'
  printf '%s' "${PARALLEL_API_KEY}" | gcloud secrets versions add parallel-api-key --data-file=-
  unset PARALLEL_API_KEY
fi
for secret in cutline-session-secret parallel-api-key; do
  gcloud secrets add-iam-policy-binding "${secret}" --member="serviceAccount:${SERVICE_ACCOUNT}" --role=roles/secretmanager.secretAccessor >/dev/null
done

gcloud firestore fields ttls update expires_at --collection-group=cutline_projects --enable-ttl --quiet
echo "Bootstrap complete. Next run ./scripts/deploy_cloud_run.sh"
