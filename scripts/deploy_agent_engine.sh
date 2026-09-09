#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
MODEL_ID="${MODEL_ID:-gemini-2.5-flash}"
AGENT_ENGINE_ID="${AGENT_ENGINE_ID:-}"
CREATE_AGENT_ENGINE="${CREATE_AGENT_ENGINE:-false}"
export GOOGLE_GENAI_USE_VERTEXAI=TRUE GOOGLE_CLOUD_PROJECT GOOGLE_CLOUD_LOCATION MODEL_ID

command -v adk >/dev/null || { echo "Run: pip install ." >&2; exit 1; }
command -v gcloud >/dev/null || { echo "Google Cloud CLI is required." >&2; exit 1; }
python -c 'import vertexai; from vertexai.agent_engines.templates.adk import AdkApp' >/dev/null || {
  echo "Agent Engine SDK missing. Run: pip install ." >&2
  exit 1
}

if [[ -n "${AGENT_ENGINE_ID}" ]]; then
  if [[ ! "${AGENT_ENGINE_ID}" =~ ^[0-9]+$ ]]; then
    echo "AGENT_ENGINE_ID must be the numeric ID of an existing resource." >&2
    exit 1
  fi
  echo "Updating existing Agent Engine ID: ${AGENT_ENGINE_ID}"
elif [[ "${CREATE_AGENT_ENGINE,,}" != "true" ]]; then
  echo "Refusing an implicit Agent Engine creation." >&2
  echo "Set AGENT_ENGINE_ID to update an existing resource, or CREATE_AGENT_ENGINE=true for the first creation." >&2
  exit 1
else
  echo "Explicit first-time Agent Engine creation requested."
fi

gcloud services enable \
  aiplatform.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --quiet

gcloud secrets describe parallel-api-key --project="${GOOGLE_CLOUD_PROJECT}" >/dev/null
if [[ -z "$(gcloud secrets versions list parallel-api-key --project="${GOOGLE_CLOUD_PROJECT}" --filter='state=ENABLED' --format='value(name)' --limit=1)" ]]; then
  echo "parallel-api-key has no enabled Secret Manager version." >&2
  exit 1
fi

PROJECT_NUMBER="$(gcloud projects describe "${GOOGLE_CLOUD_PROJECT}" --format='value(projectNumber)')"
AGENT_ENGINE_IDENTITY="service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"

gcloud beta services identity create \
  --service=aiplatform.googleapis.com \
  --project="${GOOGLE_CLOUD_PROJECT}" >/dev/null

PROJECT_ROLE_READY=false
for _ in {1..24}; do
  if gcloud projects add-iam-policy-binding "${GOOGLE_CLOUD_PROJECT}" \
    --member="serviceAccount:${AGENT_ENGINE_IDENTITY}" \
    --role=roles/aiplatform.reasoningEngineServiceAgent \
    --condition=None \
    --quiet >/dev/null 2>&1; then
    PROJECT_ROLE_READY=true
    break
  fi
  sleep 5
done
if [[ "${PROJECT_ROLE_READY}" != "true" ]]; then
  echo "Unable to grant the standard Reasoning Engine service-agent role." >&2
  exit 1
fi

SECRET_ACCESS_READY=false
for _ in {1..24}; do
  if gcloud secrets add-iam-policy-binding parallel-api-key \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --member="serviceAccount:${AGENT_ENGINE_IDENTITY}" \
    --role=roles/secretmanager.secretAccessor \
    --condition=None \
    --quiet >/dev/null 2>&1; then
    SECRET_ACCESS_READY=true
    break
  fi
  sleep 5
done
if [[ "${SECRET_ACCESS_READY}" != "true" ]]; then
  echo "Unable to grant Agent Engine access to parallel-api-key." >&2
  exit 1
fi

DEPLOY_ARGS=(
  agent_engine
  --project="${GOOGLE_CLOUD_PROJECT}"
  --region="${GOOGLE_CLOUD_LOCATION}"
  --display_name="CUTLINE Claim Research"
)
if [[ -n "${AGENT_ENGINE_ID}" ]]; then
  DEPLOY_ARGS+=(--agent_engine_id="${AGENT_ENGINE_ID}")
fi
DEPLOY_ARGS+=(cutline/agents/claim_research)

DEPLOY_LOG="$(mktemp)"
trap 'rm -f "${DEPLOY_LOG}"' EXIT

set +e
adk deploy "${DEPLOY_ARGS[@]}" 2>&1 | tee "${DEPLOY_LOG}"
DEPLOY_STATUS="${PIPESTATUS[0]}"
set -e
if [[ "${DEPLOY_STATUS}" -ne 0 ]] || grep -q '^Deploy failed:' "${DEPLOY_LOG}"; then
  echo "Agent Engine deployment failed." >&2
  exit 1
fi
if [[ -n "${AGENT_ENGINE_ID}" ]] && grep -q '^Created a new instance:' "${DEPLOY_LOG}"; then
  echo "Unexpected Agent Engine creation while AGENT_ENGINE_ID was set." >&2
  exit 1
fi

RESOURCE_NAME="$(sed -n 's/^Deployed to Agent Platform: //p' "${DEPLOY_LOG}" | tail -n 1)"
if [[ -z "${RESOURCE_NAME}" ]]; then
  echo "Deployment completed without a resource name in its output." >&2
  exit 1
fi

echo "Agent Engine resource: ${RESOURCE_NAME}"
echo "Agent Engine runtime identity: ${AGENT_ENGINE_IDENTITY}"
echo "Agent Engine model: ${MODEL_ID}"
echo "Record the resource name and a successful invocation in submission evidence."
