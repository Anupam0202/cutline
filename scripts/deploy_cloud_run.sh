#!/usr/bin/env bash
set -euo pipefail
: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-cutline}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-cutline-runtime}"
MODEL_ID="${MODEL_ID:-gemini-3.5-flash}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"

gcloud config set project "${GOOGLE_CLOUD_PROJECT}"
gcloud run deploy "${SERVICE_NAME}" --source=. --region="${GOOGLE_CLOUD_LOCATION}" --service-account="${SERVICE_ACCOUNT}" --allow-unauthenticated --ingress=all --execution-environment=gen2 --port=8080 --cpu=1 --memory=1Gi --concurrency=20 --min=0 --max=10 --timeout=60 --cpu-boost --set-env-vars="APP_MODE=live,DATA_BACKEND=firestore,GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT},GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=TRUE,MODEL_ID=${MODEL_ID},COOKIE_SECURE=true,ALLOWED_HOSTS=*.run.app,PROJECT_TTL_HOURS=72,PROVIDER_TIMEOUT_SECONDS=30,LOG_LEVEL=INFO" --set-secrets="PARALLEL_API_KEY=parallel-api-key:latest,SESSION_SECRET=cutline-session-secret:latest" --startup-probe="httpGet.path=/health/ready,initialDelaySeconds=5,timeoutSeconds=5,periodSeconds=5,failureThreshold=24" --liveness-probe="httpGet.path=/health/live,initialDelaySeconds=10,timeoutSeconds=2,periodSeconds=10,failureThreshold=3" --quiet
SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --region="${GOOGLE_CLOUD_LOCATION}" --format='value(status.url)')"
echo "Deployed: ${SERVICE_URL}"
"$(dirname "$0")/smoke_test.sh" "${SERVICE_URL}"
