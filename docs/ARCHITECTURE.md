# Architecture and trust boundaries

## Decision

CUTLINE uses a deterministic application state machine around two bounded provider calls. Parallel Search supplies public source excerpts; Gemini on Vertex AI evaluates those excerpts with a strict response schema. Neither provider can approve a claim, apply a rewrite, sign off a recipe, or export reviewed work.

## Request path

1. A browser receives an HMAC-authenticated, HttpOnly session cookie and a derived CSRF token.
2. Every mutation includes the current project revision.
3. The API reads the current cue before research.
4. Parallel Search returns at most five public results.
5. CUTLINE normalizes URLs, titles, and bounded excerpts.
6. Gemini assesses only the normalized evidence packet.
7. CUTLINE validates cited indexes and requires a supporting quote to occur in a selected excerpt.
8. Firestore commits the result only if the project revision is unchanged.
9. A person separately approves the exact claim fingerprint.
10. Recipe signoff binds project title, cue order, timecodes, kinds, coverage, text, and content revisions.

## Integrity model

A claim fingerprint includes:

- claim span and proposition;
- assessment and rationale;
- exact cue text, type, timecode, and content revision;
- selected source URL, title, capture, and retrieval time;
- review policy version.

A recipe fingerprint includes project title, recipe identity and order, every cue fingerprint, and coverage. Changing any bound field invalidates current review or signoff.

## Storage

Fixture mode uses an in-process memory store. Live mode requires Firestore and will not start with memory storage. Firestore transactions combine revision comparison and write, preventing two same-revision mutations from both succeeding. Project documents include `expires_at` for TTL cleanup and can be deleted immediately by the owning session.

## Identity model

The public demo is intentionally anonymous. A random session identifier is authenticated with HMAC and never stored directly; Firestore stores a derived owner hash. This isolates browser sessions without collecting personal identity. A production studio deployment can place Identity-Aware Proxy or an organization authentication layer in front of the same API.

## Provider boundaries

- The Parallel key is server-side and comes from Secret Manager.
- Vertex AI uses the Cloud Run service account through Application Default Credentials.
- Source excerpts are treated as untrusted data.
- Provider request bodies, responses, keys, and source content are not logged.
- Result count, text length, timeout, and output schema are bounded.
- Provider errors return a retryable state and never become synthetic success.

## Failure behavior

| Failure | Behavior |
|---|---|
| Missing live configuration | Process startup fails before serving traffic |
| Firestore unavailable | Readiness fails; Cloud Run removes the instance from service |
| Parallel timeout/error | Research returns a provider error; project remains unchanged |
| Gemini timeout/error | Research returns a provider error; project remains unchanged |
| No usable search result | Stored assessment is `INSUFFICIENT`; no approval permitted |
| Invalid model citation | Assessment is downgraded to `INSUFFICIENT` |
| Concurrent edit during research | Transaction returns a revision conflict; stale result is discarded |
| Cross-site mutation | CSRF/origin check rejects the request |
| Stale review at export | Export returns conflict and no artifact |

## Deployment

Cloud Run runs one Uvicorn process per instance and relies on platform autoscaling. Firestore provides shared state across instances. Concurrency is deliberately lower than the server limit to preserve provider latency and cost. Startup and liveness probes are separate. The runtime container is non-root and has no persistent local writes.
