# Google Cloud production setup

This guide creates the resources CUTLINE needs without placing credentials in the repository. Commands assume Bash and the Google Cloud CLI.

## 1. Collect the required values

Choose and record:

```bash
export GOOGLE_CLOUD_PROJECT='your-unique-project-id'
export GOOGLE_CLOUD_LOCATION='us-central1'   # Cloud Run and Agent Engine region
export FIRESTORE_LOCATION='nam5'             # choose once; cannot be changed
export SERVICE_NAME='cutline'
export SERVICE_ACCOUNT_NAME='cutline-runtime'
```

Use a dedicated billing-enabled project. Vertex AI calls use the Cloud Run service identity through Application Default Credentials; no Google API key is required.

## 2. Select the project and verify authentication

Google Cloud Shell is the recommended deployment environment. It already includes an authenticated Google Cloud CLI, so do not run interactive login commands there.

```bash
gcloud version
gcloud auth list --filter=status:ACTIVE --format='value(account)'
gcloud config set project "$GOOGLE_CLOUD_PROJECT"
gcloud config set run/region "$GOOGLE_CLOUD_LOCATION"
gcloud projects describe "$GOOGLE_CLOUD_PROJECT" --format='value(lifecycleState)'
gcloud billing projects describe "$GOOGLE_CLOUD_PROJECT" --format='value(billingEnabled)'
```

For a local workstation only, authenticate with `gcloud auth login` and `gcloud auth application-default login` before running local credentialed tests.

Create a new project only if needed:

```bash
gcloud projects create "$GOOGLE_CLOUD_PROJECT" --name='CUTLINE Production'
gcloud billing projects link "$GOOGLE_CLOUD_PROJECT" --billing-account='YOUR_BILLING_ACCOUNT_ID'
```

List billing accounts with `gcloud billing accounts list`. Do not continue until billing is enabled.

## 3. Enable APIs

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  artifactregistry.googleapis.com \
  billingbudgets.googleapis.com \
  cloudbuild.googleapis.com \
  cloudresourcemanager.googleapis.com \
  firestore.googleapis.com \
  iam.googleapis.com \
  logging.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com
```

## 4. Create Firestore

```bash
gcloud firestore databases create \
  --database='(default)' \
  --location="$FIRESTORE_LOCATION" \
  --type=firestore-native

gcloud firestore fields ttls update expires_at \
  --collection-group=cutline_projects \
  --enable-ttl
```

The application also supports immediate deletion from the UI. TTL is eventual cleanup, not an immediate erasure guarantee.

## 5. Create the runtime identity

```bash
RUNTIME_SA="${SERVICE_ACCOUNT_NAME}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"

gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
  --display-name='CUTLINE runtime'

for ROLE in roles/aiplatform.user roles/datastore.user roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="$ROLE" \
    --condition=None
done
```

Do not grant Owner, Editor, service-account-key creation, or broad Secret Manager access.

## 6. Create secrets

Get a Parallel API key from the Parallel platform. Store it without echoing it or adding it to shell history:

```bash
gcloud secrets create parallel-api-key --replication-policy=automatic
read -r -s -p 'Parallel API key: ' PARALLEL_API_KEY; printf '\n'
printf '%s' "$PARALLEL_API_KEY" | \
  gcloud secrets versions add parallel-api-key --data-file=-
unset PARALLEL_API_KEY

gcloud secrets create cutline-session-secret --replication-policy=automatic
openssl rand -base64 48 | \
  gcloud secrets versions add cutline-session-secret --data-file=-
```

Grant the runtime identity access to these two secrets only:

```bash
for SECRET in parallel-api-key cutline-session-secret; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role=roles/secretmanager.secretAccessor
done
```

Verify metadata—not values:

```bash
gcloud secrets versions list parallel-api-key
gcloud secrets versions list cutline-session-secret
```

## 7. Confirm the Gemini model

Open Vertex AI Model Garden in the selected project and verify that `gemini-3.5-flash` is available at the global endpoint. If the project exposes a different generally available Gemini model, set it explicitly:

```bash
export MODEL_ID='gemini-3.5-flash'
```

Keep the model identifier in deployment configuration so a model change creates a new Cloud Run revision.

## 8. Validate locally with cloud credentials

Use a separate terminal and never commit `.env`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'

export APP_MODE=live
export DATA_BACKEND=firestore
export GOOGLE_CLOUD_PROJECT
export GOOGLE_CLOUD_LOCATION=global
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export MODEL_ID
read -r -s -p 'Parallel API key: ' PARALLEL_API_KEY; printf '\n'
export PARALLEL_API_KEY
export SESSION_SECRET="$(openssl rand -base64 48)"
export COOKIE_SECURE=false
export ALLOWED_HOSTS=localhost,127.0.0.1

uvicorn cutline.main:app --host 127.0.0.1 --port 8080
```

After testing, unset the local key: `unset PARALLEL_API_KEY SESSION_SECRET`.

## 9. Deploy the web application to Cloud Run

Run the included deployment script:

```bash
export GOOGLE_CLOUD_PROJECT
export GOOGLE_CLOUD_LOCATION='us-central1'
export MODEL_ID='gemini-3.5-flash'
./scripts/deploy_cloud_run.sh
```

Equivalent core command:

```bash
gcloud run deploy cutline \
  --source=. \
  --region="$GOOGLE_CLOUD_LOCATION" \
  --service-account="$RUNTIME_SA" \
  --allow-unauthenticated \
  --execution-environment=gen2 \
  --cpu=1 --memory=1Gi --concurrency=20 --min=0 --max=10 --timeout=60 \
  --set-env-vars="APP_MODE=live,DATA_BACKEND=firestore,GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT},GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=TRUE,MODEL_ID=${MODEL_ID},COOKIE_SECURE=true,ALLOWED_HOSTS=*.run.app" \
  --set-secrets="PARALLEL_API_KEY=parallel-api-key:latest,SESSION_SECRET=cutline-session-secret:latest"
```

Retrieve the immutable deployment identifiers:

```bash
SERVICE_URL="$(gcloud run services describe cutline --format='value(status.url)')"
REVISION="$(gcloud run services describe cutline --format='value(status.latestReadyRevisionName)')"
printf 'URL: %s\nRevision: %s\n' "$SERVICE_URL" "$REVISION"
```

Use both in release evidence.

## 10. Deploy the Google ADK agent to Agent Engine

The agent directory exports `root_agent` and its tool calls Parallel Search.

```bash
source .venv/bin/activate
export GOOGLE_CLOUD_PROJECT
export GOOGLE_CLOUD_LOCATION='us-central1'
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export MODEL_ID='gemini-2.5-flash'
export CREATE_AGENT_ENGINE=true
./scripts/deploy_agent_engine.sh
unset CREATE_AGENT_ENGINE
```

For an update, omit `CREATE_AGENT_ENGINE`, set `AGENT_ENGINE_ID` to the existing numeric resource ID, and rerun the script. The script refuses implicit creation, so a delayed post-deployment IAM check cannot accidentally lead to a duplicate resource.

`gemini-2.5-flash` is used because the Agent Engine is deployed in `us-central1`; select a model available in the same endpoint location.

Do not export the Parallel credential for the remote deployment. The ADK tool retrieves `parallel-api-key` from Secret Manager at runtime using the Agent Engine identity; the deployment script grants that identity access only to this secret.

The command prints an Agent Engine resource name similar to:

```text
projects/PROJECT_NUMBER/locations/REGION/reasoningEngines/RESOURCE_ID
```

Record the resource name and a successful test invocation. Do not publish credentials or raw private request content.

## 11. Run the credentialed release checks

```bash
./scripts/smoke_test.sh "$SERVICE_URL"
curl --fail "$SERVICE_URL/health/live"
curl --fail "$SERVICE_URL/health/ready"
```

Then use a clean browser:

1. Confirm the header says **Live · Gemini + Parallel**.
2. Open the sample and change July 16 to July 20.
3. Confirm Main cut and Teaser become stale while Independent control remains current.
4. Run research.
5. Confirm the receipt shows both provider calls and the evidence links are public.
6. Apply the repair, research again, approve, sign off, and export.
7. Open the same project after forcing a new Cloud Run instance and verify Firestore persistence.
8. Delete the project and verify its Firestore document is gone.

## 12. Add cost and availability guardrails

Create a small budget with notifications appropriate to the event credits:

```bash
gcloud billing budgets create \
  --billing-account='YOUR_BILLING_ACCOUNT_ID' \
  --display-name='CUTLINE hackathon budget' \
  --budget-amount='50USD' \
  --threshold-rule=percent=0.50 \
  --threshold-rule=percent=0.90 \
  --threshold-rule=percent=1.00
```

Keep Cloud Run `max=10`, provider timeouts at 30 seconds, and five Parallel results. Set `min=1` only for the judging window if cold-start latency is unacceptable and the budget permits it:

```bash
gcloud run services update cutline --min=1
```

## 13. Optional custom domain

After mapping a verified domain, update the allowed hosts and deploy a new revision:

```bash
gcloud run domain-mappings create --service=cutline --domain='cutline.example.com'
gcloud run services update cutline \
  --update-env-vars='ALLOWED_HOSTS=cutline.example.com'
```

Retain the generated `run.app` URL for judge fallback if allowed-host configuration includes it.

## Values required for final submission

- Google Cloud project ID
- Cloud Run region
- Cloud Run HTTPS URL
- Latest ready revision name
- Runtime service account email
- Gemini model ID
- Agent Engine resource name
- Public GitHub repository URL
- Public YouTube or Vimeo demo URL
- Parallel track selection
- Devpost submission receipt
