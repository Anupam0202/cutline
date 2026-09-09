#!/usr/bin/env bash
set -euo pipefail
: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
export GOOGLE_GENAI_USE_VERTEXAI=TRUE GOOGLE_CLOUD_PROJECT GOOGLE_CLOUD_LOCATION
command -v adk >/dev/null || { echo "Run: pip install ." >&2; exit 1; }
adk deploy agent_engine --project="${GOOGLE_CLOUD_PROJECT}" --region="${GOOGLE_CLOUD_LOCATION}" --display_name="CUTLINE Claim Research" cutline/agents/claim_research
echo "Record the returned Agent Engine resource ID in submission evidence."
