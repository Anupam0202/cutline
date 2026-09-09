# Hackathon submission guide

## Recommended title

**CUTLINE — Change control for documentary facts**

## One-line pitch

CUTLINE prevents stale fact-check approvals from surviving documentary script edits by binding every claim review to exact narration, live evidence, and edit recipes.

## Devpost description

Documentary facts are not static: narration changes throughout the edit, but approvals often remain simple checkboxes. CUTLINE turns fact review into versioned change control. A single date change invalidates only the claims and editor handoffs that depend on that wording. The application then calls Parallel Search for traceable public evidence, uses Gemini on Vertex AI to produce a structured assessment, requires explicit human approval, and exports a timecoded paper-edit handoff with before/after text, sources, re-recording tasks, and scope limits.

The web application runs on Google Cloud Run, stores transactional project state in Firestore, injects credentials from Secret Manager, and includes a Google ADK agent deployable to Vertex AI Agent Engine. The runtime is bounded by strict schemas, source-validation rules, provider timeouts, revision preconditions, CSRF protection, and fail-closed configuration. Research can propose a repair but cannot approve, publish, or change quotations.

The key learning was that evidence quality alone is not enough: approval must also be bound to the exact content and edit recipe that will be delivered. CUTLINE makes that dependency visible to producers, researchers, and editors.

## Three-minute demo

**0:00–0:20 — Problem**  
Show the hero. Explain that a reviewed fact can become stale after one word changes.

**0:20–0:40 — Product boundary**  
Open the workspace. Point out exact revision, human approval, and immutable quotations.

**0:40–1:05 — Signature edit**  
Change July 16 to July 20. Show Main cut and Teaser turn stale while Independent control remains current.

**1:05–1:45 — Live agent workflow**  
Run research. Keep the provider receipt visible. Show that Parallel Search and Gemini on Vertex AI were called, then inspect source excerpts and links.

**1:45–2:20 — Human control**  
Show the contradicted assessment and supported repair. Apply it, explain why prior review becomes stale again, rerun research, and approve the exact corrected claim.

**2:20–2:45 — Handoff**  
Sign off recipes and download JSON or CSV. Show timecodes, before/after wording, re-record flags, sources, and disclaimer.

**2:45–3:00 — Architecture and impact**  
Show the Cloud Run service, Agent Engine resource, and repository. Close on the audience: documentary researchers, producers, and editors.

## Evidence to capture

- Cloud Run URL in a signed-out browser
- Latest ready Cloud Run revision
- Runtime badge showing live integrations
- Provider receipt after a fresh research action
- Public source links corresponding to displayed excerpts
- Firestore project document before and after delete
- Agent Engine resource and successful invocation
- GitHub dependency imports and active call path
- MIT license visible in the GitHub About panel
- CI green on the submitted commit

Redact keys, session cookies, internal project numbers if not needed, and private request content.

## Final checklist

- [ ] Entrant and every team member satisfy the official eligibility rules.
- [ ] Project was created within the contest period and the submitted commit is frozen.
- [ ] Parallel track selected.
- [ ] Hosted HTTPS project URL works in a clean browser.
- [ ] Normal demo workflow makes fresh Parallel Search and Gemini Vertex AI calls.
- [ ] Agent Builder/Agent Engine deployment evidence is included.
- [ ] Public GitHub repository contains all source and instructions.
- [ ] MIT license is detected at repository top level and selected in About.
- [ ] No credentials, private data, local-only files, or development traces are committed.
- [ ] Public YouTube/Vimeo video is no longer than three minutes and has English audio or subtitles.
- [ ] Devpost description names features, technologies, data sources, findings, and learnings.
- [ ] Hosted, repository, and video links are tested after publication.
- [ ] Service is funded and monitored through the judging window.
- [ ] Submission receipt and exact commit SHA are saved.
