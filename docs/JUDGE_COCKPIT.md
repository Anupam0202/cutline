# Judge-ready review cockpit

This upgrade turns CUTLINE's deterministic Apollo proof into a broader, resumable documentary review product without weakening the existing human-control boundaries.

## What changed

- A redesigned landing experience explains the four-step agent path before the first click.
- The original Apollo 11 proof remains the primary, deterministic judging path.
- Editors can create a bounded custom review from 1–12 narration cues.
- Private-session project summaries make active reviews resumable after refresh.
- A review scoreboard exposes progress, current claims, blocked handoffs, and captured evidence.
- The impact stage visualizes cue → claim → recipe dependencies.
- Evidence cards expose source domains, excerpts, retrieval metadata, and safe outbound links.
- The runtime receipt separates Parallel Search, Gemini assessment, and the human release gate.
- A versioned ledger explains every state transition and can be copied as a compact audit summary.
- Responsive layouts, focus treatment, status announcements, loading feedback, and dark mode improve judge and editor usability.

## Added endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/project-summaries` | Return bounded summaries for projects owned by the private browser session |
| `POST` | `/api/custom-projects` | Create a validated custom narration review |

Custom reviews require a title and 1–12 ascending, non-overlapping cues. Every narration cue starts unassessed; quotation cues remain annotation-only. The existing revision precondition, CSRF check, owner isolation, TTL, research, approval, signoff, and export gates continue to apply.

## Judging alignment

### Technological implementation

Parallel Search is called at runtime for public evidence; Gemini assesses the bounded evidence packet; Google ADK packages the agent; Cloud Run serves the API; Firestore stores transactionally revisioned state. The UI now makes those boundaries and receipts visible instead of asking judges to infer them.

### Design

The cockpit presents one coherent path from script to impact to evidence to handoff. It communicates stale state, the next safe action, provider activity, and human authority in product language.

### Potential impact

Documentary researchers and post-production teams can see exactly which narration changes invalidate evidence and downstream cut recipes. That reduces accidental reuse of stale fact checks and creates a review record that can travel with an editorial handoff.

### Quality of the idea

CUTLINE treats factual review as revision-aware production infrastructure rather than a one-off chatbot answer. Parallel is the evidence acquisition layer, Gemini is the constrained assessment layer, and people retain release authority.

## Recommended three-minute proof

1. **0:00–0:25** — Open the landing page; point to the live stack and human-gated workflow.
2. **0:25–0:45** — Select **Run the Apollo 11 proof**; show the baseline scoreboard and policy marker.
3. **0:45–1:05** — Select **Make the one-word edit**; show the dependency graph and blocked handoffs.
4. **1:05–1:35** — Select **Research changed claim**; show Parallel source domains and the Gemini receipt.
5. **1:35–1:55** — Apply the supported repair, confirm it, then research the corrected wording again.
6. **1:55–2:20** — Select **Human: approve exact claim**, then **Sign off current recipes**.
7. **2:20–2:40** — Show the audit ledger and download the JSON handoff.
8. **2:40–3:00** — Briefly open **Review your own script** to prove the product is reusable beyond the canned example.

The hosted service must be updated only after the pull request is green and merged. Preserve the currently validated Cloud Run revision for rollback.
