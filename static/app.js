"use strict";

const select = (selector) => document.querySelector(selector);
const state = {
  csrf: "",
  capabilities: null,
  project: null,
  step: "script",
  selectedCueId: "c1",
  busy: false,
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function safeSourceUrl(value) {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

async function api(path, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.headers || {}),
  };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (state.csrf) {
    headers["X-CSRF-Token"] = state.csrf;
  }
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = response.status === 204
    ? {}
    : contentType.includes("application/json")
      ? await response.json()
      : await response.text();
  if (!response.ok) {
    const message = payload?.error?.message || `Request failed (${response.status}).`;
    const error = new Error(message);
    error.code = payload?.error?.code || "REQUEST_FAILED";
    throw error;
  }
  return payload;
}

function timecode(milliseconds) {
  const totalSeconds = Math.floor(milliseconds / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return [hours, minutes, seconds].map((value) => String(value).padStart(2, "0")).join(":");
}

function claimForCue(cueId) {
  return Object.values(state.project.claims).find((claim) => claim.cue_id === cueId);
}

function selectedClaim() {
  return claimForCue(state.selectedCueId) || Object.values(state.project.claims)[0];
}

function setBusy(busy, message = "") {
  state.busy = busy;
  select("#workspace")?.setAttribute("aria-busy", String(busy));
  document.querySelectorAll("button").forEach((button) => {
    if (!button.closest("dialog")) button.disabled = busy;
  });
  if (message) setStatus(message, "");
}

function setStatus(message, variant = "") {
  const banner = select("#statusBanner");
  if (!banner) return;
  banner.className = `status-banner${variant ? ` ${variant}` : ""}`;
  banner.textContent = message;
}

function renderStatus() {
  const staleClaims = state.project.stale_claim_ids.length;
  const staleRecipes = Object.values(state.project.recipes).filter((recipe) => !recipe.current).length;
  if (staleClaims) {
    setStatus(
      `${staleClaims} claim review ${staleClaims === 1 ? "is" : "are"} stale. Dependent handoffs stay blocked until evidence and human approval are current.`,
      "warning",
    );
  } else if (staleRecipes) {
    setStatus(
      `Claim evidence is current. ${staleRecipes} handoff ${staleRecipes === 1 ? "needs" : "need"} whole-recipe signoff.`,
      "warning",
    );
  } else {
    setStatus("All reviewed claims and recipe handoffs are current for this exact wording.", "success");
  }
}

function renderCues() {
  const cues = Object.values(state.project.cues);
  select("#cues").innerHTML = cues.map((cue) => {
    const claim = claimForCue(cue.id);
    const immutable = cue.kind === "QUOTATION";
    const stateLabel = immutable
      ? ["Quote · immutable", "quote"]
      : claim?.current
        ? ["Review current", "current"]
        : ["Review stale", "stale"];
    const note = immutable
      ? "Annotation only; quotation text is never rewritten."
      : String(claim?.assessment || "UNASSESSED").replaceAll("_", " ");
    return `
      <article class="cue-card${state.selectedCueId === cue.id ? " selected" : ""}">
        <time class="timecode">${timecode(cue.start_ms)}<br>${timecode(cue.end_ms)}</time>
        <div class="cue-body">
          <label for="cue-${escapeHtml(cue.id)}">${escapeHtml(cue.kind.replaceAll("_", " "))}</label>
          <textarea id="cue-${escapeHtml(cue.id)}" data-cue="${escapeHtml(cue.id)}" rows="2" ${immutable ? "readonly" : ""}>${escapeHtml(cue.text)}</textarea>
          <p class="cue-note">${escapeHtml(note)}</p>
        </div>
        <div class="cue-actions">
          <span class="state-chip ${stateLabel[1]}">${stateLabel[0]}</span>
          ${immutable ? "" : `<button class="inspect-button" type="button" data-inspect="${escapeHtml(cue.id)}">Inspect</button>`}
        </div>
      </article>`;
  }).join("");

  document.querySelectorAll("[data-cue]").forEach((textarea) => {
    textarea.addEventListener("change", () => updateCue(textarea));
  });
  document.querySelectorAll("[data-inspect]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedCueId = button.dataset.inspect;
      state.step = "evidence";
      render();
    });
  });
}

function actionButton(id, label, primary = false, disabled = false) {
  return `<button class="button${primary ? " primary" : ""}" id="${id}" type="button" ${disabled ? "disabled" : ""}>${label}</button>`;
}

function renderScriptDetail() {
  const cue = state.project.cues[state.selectedCueId] || state.project.cues.c1;
  const isFirstCue = cue.id === "c1";
  return `
    <p class="kicker">SIGNATURE MOVE</p>
    <h2>Change one date. Watch the review graph react.</h2>
    <p>${isFirstCue ? "Replace July 16 with July 20 in the first narration cue. CUTLINE invalidates only the reviews and edit recipes that depend on that wording." : "Edit this narration cue to see which reviewed claims and recipes depend on its exact revision."}</p>
    <div class="action-row">
      ${isFirstCue ? actionButton("makeEdit", "Make the one-word edit") : actionButton("inspectEvidence", "Inspect this cue", true)}
    </div>
    <p class="boundary-note"><strong>Controlled boundary</strong><br>Quoted material is immutable. Research can propose narration, but only a person can approve or apply it.</p>`;
}

function renderImpactDetail() {
  const rows = Object.values(state.project.recipes).map((recipe) => `
    <div class="impact-row${recipe.current ? " current" : ""}">
      <strong>${escapeHtml(recipe.name)}</strong>
      <span>${recipe.current ? "Current for this exact cue order" : "Stale — wording, evidence, or recipe signoff changed"}</span>
    </div>`).join("");
  return `
    <p class="kicker">DEPENDENCY IMPACT</p>
    <h2>Only affected handoffs become stale.</h2>
    <p>The independent control stays current when the edited cue is outside its recipe.</p>
    ${rows}
    <div class="action-row">${actionButton("researchSelected", "Research changed claim", true)}</div>`;
}

function sourceCards(claim) {
  const sources = (claim.source_ids || [])
    .map((sourceId) => state.project.sources[sourceId])
    .filter(Boolean);
  if (!sources.length) {
    return `<div class="detail-card"><strong>No current evidence</strong><small>Run research for this exact cue revision.</small></div>`;
  }
  return sources.map((source) => {
    const href = safeSourceUrl(source.url);
    return `
      <article class="source-card">
        <strong>${escapeHtml(source.title)}</strong>
        <p>“${escapeHtml(source.capture)}”</p>
        <small>${escapeHtml(source.retrieved_at)} · ${escapeHtml(source.provider.replaceAll("_", " "))}</small>
        ${href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Open source</a>` : ""}
      </article>`;
  }).join("");
}

function renderEvidenceDetail() {
  const claim = selectedClaim();
  const cue = state.project.cues[claim.cue_id];
  const assessment = String(claim.assessment).replaceAll("_", " ");
  let actions = actionButton("researchSelected", "Run evidence research", true);
  if (claim.proposal) {
    actions = actionButton("applyProposal", "Apply supported repair", true) + actionButton("researchSelected", "Research again");
  } else if (claim.evidence_current && !claim.current && ["SUPPORTED", "SUPPORTED_DEMO"].includes(claim.assessment)) {
    actions = actionButton("approveSelected", "Human: approve exact claim", true);
  } else if (claim.current && Object.values(state.project.recipes).some((recipe) => !recipe.current)) {
    actions = actionButton("signoffRecipes", "Sign off current recipes", true);
  }
  const proposal = claim.proposal ? `
    <div class="detail-card">
      <strong>Supported narration repair</strong>
      <p>${escapeHtml(claim.proposal.new_text)}</p>
      <small>Requires re-recording. Existing picture and audio are unchanged.</small>
    </div>` : "";
  return `
    <p class="kicker">INSPECTABLE EVIDENCE · ${escapeHtml(cue.id.toUpperCase())}</p>
    <h2>${escapeHtml(assessment)}</h2>
    <p>${escapeHtml(claim.rationale || "This wording has not been researched for the current revision.")}</p>
    ${sourceCards(claim)}
    ${proposal}
    <div class="action-row">${actions}</div>
    <p class="boundary-note">Evidence is a captured excerpt with its source URL and retrieval time. A provider response never becomes human approval automatically.</p>`;
}

function renderHandoffDetail() {
  const current = state.project.recipes.main.current;
  return `
    <p class="kicker">EDITOR HANDOFF</p>
    <h2>${current ? "Current paper edit" : "Reviewed export blocked"}</h2>
    <p>${current ? "The main-cut recipe is current. Export carries timecodes, before/after wording, source captures, re-record flags, and scope limits." : "Resolve stale claim reviews and sign off the whole recipe before downloading a reviewed handoff."}</p>
    <div class="action-row">
      ${actionButton("exportJson", "Download JSON", true, !current)}
      ${actionButton("exportCsv", "Download CSV", false, !current)}
      ${actionButton("exportText", "Download text", false, !current)}
    </div>
    <p class="boundary-note"><strong>Not certified</strong><br>No assertion is made about rights, legal clearance, publisher authenticity, audiovisual edits, or universal truth.</p>`;
}

function renderDetail() {
  const renderers = {
    script: renderScriptDetail,
    impact: renderImpactDetail,
    evidence: renderEvidenceDetail,
    handoff: renderHandoffDetail,
  };
  select("#detail").innerHTML = renderers[state.step]();
  bindDetailActions();
}

function receiptForSelected() {
  return selectedClaim()?.provider_receipt || {};
}

function renderIntegrations() {
  const receipt = receiptForSelected();
  const live = state.capabilities?.mode === "LIVE";
  const parallelCalled = Boolean(receipt.parallel_called);
  const geminiCalled = Boolean(receipt.gemini_called);
  const synthetic = receipt.kind === "SYNTHETIC_FIXTURE" || receipt.kind === "CURATED_SAMPLE";
  const cards = [
    {
      name: live ? "Parallel Search" : "Evidence fixture",
      detail: parallelCalled
        ? `Search completed${receipt.parallel_duration_ms ? ` · ${receipt.parallel_duration_ms} ms` : ""}`
        : synthetic ? "No external request for this baseline" : "Waiting for research",
      called: parallelCalled,
    },
    {
      name: live ? "Gemini on Vertex AI" : "Assessment fixture",
      detail: geminiCalled
        ? `${escapeHtml(receipt.gemini_model || "Gemini")} completed${receipt.gemini_duration_ms ? ` · ${receipt.gemini_duration_ms} ms` : ""}`
        : synthetic ? "Deterministic sample assessment" : "Waiting for evidence",
      called: geminiCalled,
    },
  ];
  select("#integrationCards").innerHTML = cards.map((card) => `
    <div class="integration-card">
      <div><strong>${escapeHtml(card.name)}</strong><small>${card.detail}</small></div>
      <span class="provider-badge ${card.called ? "called" : "waiting"}">${card.called ? "Called" : "Idle"}</span>
    </div>`).join("");
}

function render() {
  if (!state.project) return;
  select("#revision").textContent = `Revision ${state.project.revision}`;
  document.querySelectorAll("[data-step]").forEach((button) => {
    const active = button.dataset.step === state.step;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "step" : "false");
  });
  renderStatus();
  renderCues();
  renderDetail();
  renderIntegrations();
}

function bindDetailActions() {
  select("#makeEdit")?.addEventListener("click", () => {
    const input = select("#cue-c1");
    input.value = input.value.replace("July 16", "July 20");
    input.dispatchEvent(new Event("change"));
  });
  select("#inspectEvidence")?.addEventListener("click", () => {
    state.step = "evidence";
    render();
  });
  select("#researchSelected")?.addEventListener("click", researchSelected);
  select("#approveSelected")?.addEventListener("click", approveSelected);
  select("#applyProposal")?.addEventListener("click", () => select("#confirmDialog").showModal());
  select("#signoffRecipes")?.addEventListener("click", signoffRecipes);
  select("#exportJson")?.addEventListener("click", () => download("json"));
  select("#exportCsv")?.addEventListener("click", () => download("csv"));
  select("#exportText")?.addEventListener("click", () => download("text"));
}

async function runAction(work, nextStep, message) {
  if (state.busy) return;
  setBusy(true, message);
  try {
    state.project = await work();
    state.step = nextStep;
    render();
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
    document.querySelectorAll("button").forEach((button) => { button.disabled = false; });
    render();
  }
}

async function updateCue(textarea) {
  state.selectedCueId = textarea.dataset.cue;
  await runAction(
    () => api(`/api/projects/${state.project.id}/cues/${textarea.dataset.cue}`, {
      method: "PATCH",
      body: JSON.stringify({ expected_revision: state.project.revision, text: textarea.value }),
    }),
    "impact",
    "Updating the cue and recalculating dependent handoffs…",
  );
}

async function researchSelected() {
  const cueId = selectedClaim().cue_id;
  await runAction(
    () => api(`/api/projects/${state.project.id}/cues/${cueId}/research`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: state.project.revision }),
    }),
    "evidence",
    state.capabilities.mode === "LIVE"
      ? "Searching with Parallel and assessing the evidence with Gemini…"
      : "Running the deterministic evidence fixture…",
  );
}

async function approveSelected() {
  const cueId = selectedClaim().cue_id;
  await runAction(
    () => api(`/api/projects/${state.project.id}/cues/${cueId}/review`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: state.project.revision }),
    }),
    "evidence",
    "Binding human approval to this exact cue and evidence set…",
  );
}

async function applySelectedProposal() {
  const cueId = selectedClaim().cue_id;
  await runAction(
    () => api(`/api/projects/${state.project.id}/cues/${cueId}/apply`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: state.project.revision, confirmed: true }),
    }),
    "evidence",
    "Applying the narration repair and invalidating prior review…",
  );
}

async function signoffRecipes() {
  await runAction(
    () => api(`/api/projects/${state.project.id}/signoff`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: state.project.revision }),
    }),
    "handoff",
    "Binding whole-recipe signoff to the current paper edit…",
  );
}

function download(format) {
  window.location.assign(`/api/projects/${state.project.id}/export?format=${format}`);
}

async function startProject() {
  setBusy(true);
  try {
    state.project = await api("/api/projects", { method: "POST", body: "{}" });
    select("#workspace").hidden = false;
    select("#workspace").focus();
    state.step = "script";
    state.selectedCueId = "c1";
    render();
  } catch (error) {
    select("#start").disabled = false;
    select("#retention").textContent = error.message;
  } finally {
    state.busy = false;
    document.querySelectorAll("button").forEach((button) => { button.disabled = false; });
  }
}

async function deleteProject() {
  if (!state.project || !window.confirm("Delete this project and its stored review state?")) return;
  setBusy(true, "Deleting this project…");
  try {
    await api(`/api/projects/${state.project.id}`, { method: "DELETE" });
    state.project = null;
    select("#workspace").hidden = true;
    select("#intro").scrollIntoView({ block: "start" });
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    state.busy = false;
    document.querySelectorAll("button").forEach((button) => { button.disabled = false; });
  }
}

async function initialize() {
  try {
    state.capabilities = await api("/api/capabilities");
    state.csrf = state.capabilities.csrf;
    const runtime = select("#runtime");
    const live = state.capabilities.mode === "LIVE";
    runtime.classList.toggle("live", live);
    runtime.querySelector("span:last-child").textContent = live
      ? "Live · Gemini + Parallel"
      : "Practice · synthetic evidence";
    select("#retention").textContent = `Private session · ${state.capabilities.limits.retention_hours}h retention`;
  } catch {
    select("#runtime").querySelector("span:last-child").textContent = "Service unavailable";
    select("#start").disabled = true;
  }
}

document.querySelectorAll("[data-step]").forEach((button) => {
  button.addEventListener("click", () => {
    state.step = button.dataset.step;
    render();
  });
});
select("#start").addEventListener("click", startProject);
select("#deleteProject").addEventListener("click", deleteProject);
select("#confirmForm").addEventListener("submit", (event) => {
  if (event.submitter?.value === "confirm") {
    event.preventDefault();
    select("#confirmDialog").close();
    applySelectedProposal();
  }
});

initialize();
