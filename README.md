# CUTLINE

**Version-bound documentary fact review for editorial teams**

CUTLINE prevents an old fact-check approval from silently surviving a later script edit. It binds every claim review to the exact cue text, evidence capture, content revision, and edit recipe that a person approved.

**Hackathon track:** Parallel  
**Google runtime:** Gemini on Vertex AI, with a deployable Google ADK agent  
**Partner runtime:** Parallel Search API  
**Deployment target:** Google Cloud Run with Firestore

## Why it matters

Documentary teams routinely revise narration after research. A date, qualifier, or attribution can change while an existing “checked” flag remains green. CUTLINE treats fact review as change control:

1. Review a timecoded paper edit.
2. Change one word or date.
3. Invalidate only dependent claims and cut recipes.
4. Search public evidence with Parallel.
5. Assess the captured excerpts with Gemini on Vertex AI.
6. Require explicit human approval.
7. Export a current, traceable editor handoff.

Research can propose narration, but it cannot approve, publish, or alter quoted material.

## Signature demo

The included Apollo 11 sample starts with a reviewed paper edit. Change **July 16** to **July 20** in the first narration cue:

- Main cut and teaser become stale.
- The independent control remains current.
- Research calls Parallel Search at runtime.
- Gemini assesses only the returned excerpts.
- Contradicted wording receives a proposed repair.
- Applying the repair invalidates the previous review again.
- A person approves the corrected wording and signs off the recipes.
- JSON, CSV, and text handoffs become available.

Fixture mode reproduces the workflow without credentials and labels all evidence as synthetic. Live mode fails closed unless Google Cloud, Firestore, a secure session secret, and Parallel credentials are configured.

## Architecture

```text
Browser
  │  secure session + CSRF + revision precondition
  ▼
FastAPI on Cloud Run
  ├── deterministic review state machine
  ├── Parallel Search ── public source excerpts
  ├── Gemini on Vertex AI ── structured assessment
  └── Firestore ── transactional project state + TTL

Google ADK claim-research agent
  └── deployable to Vertex AI Agent Engine
```

The public web application uses an explicit, deterministic orchestration path so that provider calls, state transitions, and human approvals remain auditable. The ADK agent in `cutline/agents/claim_research/` packages the same research capability for Agent Engine.

See [Architecture](docs/ARCHITECTURE.md) for data flow, trust boundaries, and failure behavior.

## Repository layout

```text
cutline/                       Application package
  agents/claim_research/       Google ADK agent and Parallel tool
  api.py                       HTTP routes, sessions, CSRF, headers, health checks
  domain.py                    Review fingerprints and state transitions
  providers.py                 Parallel Search and Vertex AI adapters
  store.py                     Memory and transactional Firestore stores
static/                        Accessible responsive web interface
scripts/                       GCP bootstrap, deployment, smoke, and repository checks
tests/                         Domain, API, provider, security, and concurrency tests
docs/                          Architecture, GCP setup, operations, and submission guide
```

## Local quickstart

Requirements: Python 3.12–3.14.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[test]'
cp .env.example .env
set -a && source .env && set +a
uvicorn cutline.main:app --reload --host 127.0.0.1 --port 8080
```

Open <http://127.0.0.1:8080>. The defaults run in fixture mode and make no external provider calls.

### Run validation

```bash
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
node --check static/app.js
python scripts/validate_repo.py
docker build -t cutline:local .
```

## Live configuration

| Variable | Required in live mode | Purpose |
|---|---:|---|
| `APP_MODE=live` | Yes | Enables the real provider path; no fixture fallback |
| `DATA_BACKEND=firestore` | Yes | Durable transactional state |
| `GOOGLE_CLOUD_PROJECT` | Yes | Billing and Vertex AI project |
| `GOOGLE_CLOUD_LOCATION` | Yes | Vertex AI API location; `global` is the default |
| `GOOGLE_GENAI_USE_VERTEXAI=TRUE` | Yes for ADK | Routes Google SDK calls to Vertex AI |
| `MODEL_ID` | Yes | Gemini model identifier; default `gemini-3.5-flash` |
| `PARALLEL_API_KEY` | Yes | Parallel Search credential, injected from Secret Manager |
| `SESSION_SECRET` | Yes | At least 32 random characters, injected from Secret Manager |
| `COOKIE_SECURE=true` | Yes | Secure browser session cookie |
| `ALLOWED_HOSTS` | Yes | Accepted service/custom domains |
| `PROJECT_TTL_HOURS` | No | Firestore retention window; default 72 hours |
| `PROVIDER_TIMEOUT_SECONDS` | No | Per-provider timeout; default 30 seconds |

Do not put live credentials in `.env`, shell history, screenshots, repository files, build arguments, or client-side code. Cloud Run receives both secrets from Secret Manager.

## Deploy

Follow the complete [Google Cloud setup](docs/GCP_SETUP.md), or run the reviewed scripts in order:

```bash
export GOOGLE_CLOUD_PROJECT='your-project-id'
export GOOGLE_CLOUD_LOCATION='us-central1'
./scripts/bootstrap_gcp.sh
./scripts/deploy_cloud_run.sh
./scripts/deploy_agent_engine.sh
```

The Cloud Run script builds from source, attaches a least-privilege runtime service account, injects secrets, configures resource limits and health probes, prints the HTTPS URL, and runs non-destructive smoke checks.

## API

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health/live` | Process liveness |
| `GET` | `/health/ready` | Storage readiness |
| `GET` | `/api/capabilities` | Secure session, mode, limits, integration declaration |
| `POST` | `/api/projects` | Create the bounded sample project |
| `GET` | `/api/projects/{id}` | Read owned project state |
| `PATCH` | `/api/projects/{id}/cues/{cue}` | Edit narration with revision precondition |
| `POST` | `/api/projects/{id}/cues/{cue}/research` | Call Parallel and Gemini, then store validated evidence |
| `POST` | `/api/projects/{id}/cues/{cue}/review` | Human approval of current evidence and wording |
| `POST` | `/api/projects/{id}/cues/{cue}/apply` | Confirm and apply a proposed narration repair |
| `POST` | `/api/projects/{id}/signoff` | Bind recipe signoff to exact current content |
| `GET` | `/api/projects/{id}/export` | Download reviewed JSON, CSV, or text handoff |
| `DELETE` | `/api/projects/{id}` | Delete owned project state |

Mutation requests require the session CSRF token and `expected_revision`. Firestore performs the revision check and update in one transaction.

## Security and integrity controls

- Fail-closed live configuration; no silent synthetic fallback.
- HttpOnly, Secure, SameSite session cookie with HMAC authentication.
- Derived CSRF token and same-origin mutation checks.
- Strict request models, bounded bodies, cue lengths, result counts, and provider timeouts.
- Optimistic concurrency with transactional Firestore writes.
- Content Security Policy, HSTS, frame denial, MIME sniffing prevention, and restricted browser permissions.
- No request bodies, evidence excerpts, or credentials in application logs.
- Safe source-link protocol handling and output escaping.
- CSV formula neutralization.
- Quotation immutability and explicit confirmation before narration changes.
- Human approval remains separate from provider assessment.
- Firestore TTL and explicit project deletion.
- Non-root, read-only application runtime apart from managed service clients.

See [Operations](docs/OPERATIONS.md) for rollback, secret rotation, monitoring, and incident steps.

## Production verification

Local tests cover deterministic behavior and provider boundaries. A release owner must additionally verify the credentialed environment:

1. Cloud Run readiness returns `200`.
2. The UI says **Live · Gemini + Parallel**.
3. The signature cue edit marks only dependent recipes stale.
4. Research produces a receipt showing both providers were called.
5. Displayed captures and source links correspond to the current provider response.
6. A stale response cannot commit after another edit.
7. Human approval and recipe signoff are required before export.
8. Firestore persists state across a new Cloud Run instance.
9. TTL and explicit deletion remove project records.
10. Cloud Logging contains timing and error type only—no keys or content.

Do not claim live end-to-end validation until these checks are completed in the target project.

## Publish to GitHub

```bash
git init
git branch -M main
git add .
git commit -m "Release CUTLINE 1.0.0"
gh repo create cutline --public --source=. --remote=origin --push
gh repo edit --description "Version-bound documentary fact review with Gemini and Parallel Search" --add-topic google-cloud --add-topic gemini --add-topic parallel --add-topic media-tech
```

If `cutline` is unavailable, use `cutline-cinema` consistently in the repository URL and Devpost form. Add the MIT license in the GitHub About panel, enable secret scanning and Dependabot alerts, then protect `main` with the CI workflow as a required check.

## Submission

Use [Submission guide](docs/SUBMISSION.md) for the three-minute demo outline, Devpost copy, runtime evidence checklist, and final link verification.

## License

Original CUTLINE code is available under the [MIT License](LICENSE). Dependency notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
