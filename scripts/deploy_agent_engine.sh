#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
export GOOGLE_GENAI_USE_VERTEXAI=TRUE GOOGLE_CLOUD_PROJECT GOOGLE_CLOUD_LOCATION

command -v adk >/dev/null || { echo "Run: pip install ." >&2; exit 1; }
gcloud secrets describe parallel-api-key >/dev/null
if [[ -z "$(gcloud secrets versions list parallel-api-key --filter='state=ENABLED' --format='value(name)' --limit=1)" ]]; then
  echo "parallel-api-key has no enabled Secret Manager version." >&2
  exit 1
fi

adk deploy agent_engine \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --display_name="CUTLINE Claim Research" \
  cutline/agents/claim_research

PROJECT_NUMBER="$(gcloud projects describe "${GOOGLE_CLOUD_PROJECT}" --format='value(projectNumber)')"
AGENT_ENGINE_IDENTITY="service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
for _ in {1..12}; do
  if gcloud iam service-accounts describe "${AGENT_ENGINE_IDENTITY}" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done
if ! gcloud iam service-accounts describe "${AGENT_ENGINE_IDENTITY}" >/dev/null 2>&1; then
  echo "Agent Engine identity was not available for Secret Manager permission." >&2
  exit 1
fi

gcloud secrets add-iam-policy-binding parallel-api-key \
  --member="serviceAccount:${AGENT_ENGINE_IDENTITY}" \
  --role=roles/secretmanager.secretAccessor \
  --quiet >/dev/null

echo "Agent Engine runtime identity: ${AGENT_ENGINE_IDENTITY}"
echo "Record the returned Agent Engine resource ID and a successful invocation in submission evidence."
