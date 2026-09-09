# Security policy

## Supported version

Security fixes are applied to the current `1.x` release line.

## Reporting

Do not open a public issue for a suspected credential exposure or vulnerability. Contact the repository owner privately with the affected version, reproduction steps, impact, and any request ID. Do not include provider keys, session cookies, private source material, or personal data.

## Secrets

The repository must never contain `.env`, service-account keys, Parallel keys, session secrets, private keys, or copied Cloud credentials. Production secrets are injected from Google Secret Manager into the Cloud Run revision. The runtime service account has access only to the two named secrets.

## Data boundary

The public demo accepts only the included bounded narration sample. Source excerpts returned by Parallel are untrusted data and are never executed. Project records expire through Firestore TTL and can be deleted by the owning browser session.
