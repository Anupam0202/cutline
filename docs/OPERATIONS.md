# Production operations

## Release procedure

1. Run local lint, tests, JavaScript syntax, repository validation, and Docker build.
2. Merge only a green `main` branch.
3. Deploy with `scripts/deploy_cloud_run.sh`.
4. Record service URL, revision name, image digest, model ID, and Agent Engine resource ID.
5. Complete the credentialed browser workflow and save a redacted runtime receipt.
6. Route 100% traffic only after smoke and browser checks pass.

## Monitoring

Cloud Run metrics to watch:

- request count and 4xx/5xx rate;
- p50/p95/p99 latency;
- container startup latency;
- instance count and concurrency;
- memory and CPU utilization.

Application logs contain request ID, method, path, status, duration, and error type. They must not contain session tokens, request bodies, source excerpts, or provider keys.

Example error query:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="cutline"
severity>=ERROR
```

Provider degradation query:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="cutline"
(jsonPayload.message="parallel_search_failed" OR jsonPayload.message="gemini_assessment_failed")
```

## Rollback

List revisions and move traffic to the last known-good revision:

```bash
gcloud run revisions list --service=cutline --region="$GOOGLE_CLOUD_LOCATION"
gcloud run services update-traffic cutline \
  --region="$GOOGLE_CLOUD_LOCATION" \
  --to-revisions='KNOWN_GOOD_REVISION=100'
```

Do not change the submitted behavior after the deadline unless the organizer explicitly permits it. Availability-only rollback should use an already submitted revision.

## Secret rotation

Add a new version, deploy a new revision, validate, then disable the old version:

```bash
read -r -s -p 'New Parallel API key: ' KEY; printf '\n'
printf '%s' "$KEY" | gcloud secrets versions add parallel-api-key --data-file=-
unset KEY
./scripts/deploy_cloud_run.sh
gcloud secrets versions list parallel-api-key
```

Rotate `cutline-session-secret` only with awareness that existing browser sessions will be invalidated.

## Firestore retention

Verify TTL:

```bash
gcloud firestore fields ttls list --collection-group=cutline_projects
```

TTL deletion is eventual. For an immediate user request, use the UI delete action and verify that the document no longer exists.

## Incident response

1. Stop new traffic or route to a known-good revision.
2. Disable the affected secret version if credential exposure is suspected.
3. Preserve Cloud Audit Logs and request IDs; do not copy evidence content into tickets.
4. Determine whether Firestore, provider output, or export integrity was affected.
5. Notify the provider and contest organizer when required.
6. Fix, test, rotate, deploy, and document the exact new revision.

## Judging-window availability

Before September 23–October 7, 2026:

- verify billing and provider credits;
- ensure the Parallel key remains active;
- set alert thresholds;
- consider `min=1` if budget permits;
- confirm the public URL in a signed-out browser;
- preserve a known-good revision and repository tag;
- retest the video flow against the exact submitted revision.
