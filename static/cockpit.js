"use strict";

(() => {
  const nativeFetch = window.fetch.bind(window);
  let currentProject = null;
  let capabilities = null;
  let pendingCreate = null;
  let pendingResume = null;
  let latestProjectId = null;
  let enhanceQueued = false;

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);

  function queueEnhance() {
    if (enhanceQueued) return;
    enhanceQueued = true;
    window.setTimeout(() => {
      enhanceQueued = false;
      enhance();
    }, 0);
  }

  window.fetch = async (input, init = {}) => {
    let path = String(input);
    const options = { ...init };
    const method = String(options.method || "GET").toUpperCase();
    if (path === "/api/projects" && method === "POST" && pendingCreate) {
      path = "/api/custom-projects";
      options.body = JSON.stringify(pendingCreate);
      pendingCreate = null;
    } else if (path === "/api/projects" && method === "POST" && pendingResume) {
      path = `/api/projects/${encodeURIComponent(pendingResume)}`;
      options.method = "GET";
      delete options.body;
      const headers = new Headers(options.headers || {});
      headers.delete("Content-Type");
      options.headers = headers;
      pendingResume = null;
    }

    const response = await nativeFetch(path, options);
    const contentType = response.headers.get("content-type") || "";
    if (response.ok && contentType.includes("application/json")) {
      try {
        const payload = await response.clone().json();
        if (path === "/api/capabilities") {
          capabilities = payload;
          window.setTimeout(refreshProjects, 0);
        } else if (payload?.id && payload?.cues && payload?.claims) {
          currentProject = payload;
          queueEnhance();
        }
      } catch {
        // Core application owns request errors; enhancement remains optional.
      }
    }
    if (response.status === 204 && method === "DELETE") {
      currentProject = null;
      window.setTimeout(refreshProjects, 0);
    }
    return response;
  };

  function workflow() {
    const claims = Object.values(currentProject?.claims || {});
    const recipes = Object.values(currentProject?.recipes || {});
    const currentClaims = claims.filter((claim) => claim.current);
    const currentEvidence = claims.filter((claim) => claim.evidence_current);
    const currentRecipes = recipes.filter((recipe) => recipe.current);
    const sourceIds = new Set(claims.flatMap((claim) => claim.source_ids || []));
    const totalGates = claims.length * 2 + recipes.length;
    return {
      claims,
      recipes,
      currentClaims,
      currentRecipes,
      staleClaims: claims.filter((claim) => !claim.current),
      staleRecipes: recipes.filter((recipe) => !recipe.current),
      sources: sourceIds.size,
      progress: totalGates
        ? Math.round(((currentEvidence.length + currentClaims.length + currentRecipes.length) / totalGates) * 100)
        : 100,
    };
  }

  function selectedCueId() {
    return document.querySelector(".cue-card.selected [data-cue]")?.dataset.cue
      || workflow().staleClaims[0]?.cue_id
      || Object.keys(currentProject?.cues || {})[0];
  }

  function showToast(message) {
    const toast = document.querySelector("#toast");
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => { toast.hidden = true; }, 2400);
  }

  function renderMetrics(summary) {
    const values = {
      metricProgress: `${summary.progress}%`,
      metricClaims: `${summary.currentClaims.length} / ${summary.claims.length}`,
      metricRecipes: String(summary.staleRecipes.length),
      metricSources: String(summary.sources),
    };
    Object.entries(values).forEach(([id, value]) => {
      const node = document.getElementById(id);
      if (node) node.textContent = value;
    });
    const bar = document.querySelector("#metricProgressBar");
    if (bar) bar.style.width = `${summary.progress}%`;
  }

  function renderLedger() {
    const ledger = document.querySelector("#eventLedger");
    if (!ledger || !currentProject) return;
    const labels = {
      PROJECT_CREATED: ["Project created", "A private, revision-bound review was initialized."],
      CUE_EDITED: ["Narration changed", "Dependent evidence and handoffs were invalidated."],
      RESEARCH_COMPLETED: ["Evidence researched", "Parallel evidence was assessed against this cue."],
      PROPOSAL_APPLIED: ["Repair applied", "Narration changed and now requires fresh research."],
      CLAIM_APPROVED: ["Claim approved", "Human approval was bound to the exact evidence set."],
      RECIPES_SIGNED_OFF: ["Handoff signed off", "Current claims and cue order were bound to the recipe."],
    };
    const events = [...(currentProject.events || [])].reverse().slice(0, 8);
    ledger.innerHTML = events.map((event, index) => {
      const [title, description] = labels[event.type] || [event.type.replaceAll("_", " "), "State transition recorded."];
      const detail = [
        event.cue_id ? `Cue ${String(event.cue_id).toUpperCase()}` : "",
        event.assessment ? String(event.assessment).replaceAll("_", " ") : "",
        Number.isInteger(event.source_count) ? `${event.source_count} sources` : "",
        Number.isInteger(event.count) ? `${event.count} recipes` : "",
        Number.isInteger(event.cue_count) ? `${event.cue_count} cues` : "",
      ].filter(Boolean).join(" · ");
      const date = new Date(event.at);
      const time = Number.isNaN(date.getTime()) ? "Recorded" : date.toLocaleTimeString([], {
        hour: "2-digit", minute: "2-digit", second: "2-digit",
      });
      return `<article class="ledger-event"><span class="event-marker">${String(events.length - index).padStart(2, "0")}</span><div><strong>${escapeHtml(title)}</strong><p>${escapeHtml(description)}</p>${detail ? `<small>${escapeHtml(detail)}</small>` : ""}</div><time>${escapeHtml(time)}</time></article>`;
    }).join("");
  }

  function enhanceSources() {
    document.querySelectorAll(".source-card").forEach((card, index) => {
      if (card.querySelector(".source-topline")) return;
      const link = card.querySelector("a")?.href || "";
      let domain = "public source";
      try { domain = new URL(link).hostname.replace(/^www\./, ""); } catch { /* no-op */ }
      const topline = document.createElement("div");
      topline.className = "source-topline";
      topline.innerHTML = `<span>${String(index + 1).padStart(2, "0")}</span><b>${escapeHtml(domain)}</b>`;
      card.prepend(topline);
      if (card.querySelector("a")) card.querySelector("a").textContent = "Open source ↗";
    });
  }

  function enhanceIntegrations(summary) {
    const container = document.querySelector("#integrationCards");
    if (!container) return;
    [...container.children].forEach((card, index) => {
      card.classList.toggle("active", card.querySelector(".called") !== null);
      if (!card.querySelector(".integration-index")) {
        const marker = document.createElement("span");
        marker.className = "integration-index";
        marker.textContent = String(index + 1).padStart(2, "0");
        card.prepend(marker);
      }
    });
    if (!container.querySelector("[data-human-gate]")) {
      const approved = summary.staleClaims.length === 0;
      const card = document.createElement("div");
      card.className = `integration-card${approved ? " active" : ""}`;
      card.dataset.humanGate = "true";
      card.innerHTML = `<span class="integration-index">03</span><div><strong>Human release gate</strong><small>${approved ? "Exact claim fingerprints approved" : "Provider output cannot approve or export"}</small></div><span class="provider-badge ${approved ? "called" : "waiting"}">${approved ? "Approved" : "Pending"}</span>`;
      container.append(card);
    }
  }

  function enhanceImpact(summary) {
    const impactActive = document.querySelector('[data-step="impact"].active');
    const detail = document.querySelector("#detail");
    if (!impactActive || !detail || detail.querySelector(".dependency-map")) return;
    const cueId = selectedCueId();
    const cue = currentProject.cues[cueId];
    const claim = summary.claims.find((item) => item.cue_id === cueId);
    const map = document.createElement("div");
    map.className = "dependency-map";
    map.innerHTML = `<div class="dependency-node origin"><span>CUE ${escapeHtml(cueId.toUpperCase())}</span><strong>Revision ${escapeHtml(cue?.content_revision || "—")}</strong></div><i>→</i><div class="dependency-node ${claim?.current ? "current" : "stale"}"><span>CLAIM ${escapeHtml(claim?.id?.toUpperCase() || "—")}</span><strong>${claim?.current ? "Current" : "Stale"}</strong></div><i>→</i><div class="dependency-recipes">${summary.recipes.map((recipe) => `<div class="dependency-node ${recipe.current ? "current" : "stale"}"><span>${recipe.cue_ids.includes(cueId) ? "DEPENDENT CUT" : "INDEPENDENT CUT"}</span><strong>${escapeHtml(recipe.name)}</strong><small>${recipe.current ? "Current" : "Blocked"}</small></div>`).join("")}</div>`;
    detail.querySelector(".action-row")?.before(map);
  }

  function repairCustomActions(summary) {
    if (currentProject?.title !== "Apollo 11 paper edit") {
      const button = document.querySelector("#makeEdit");
      if (button) {
        button.id = "inspectCustomEvidence";
        button.textContent = "Inspect claim evidence";
        button.classList.add("primary");
        button.addEventListener("click", () => document.querySelector(`[data-inspect="${selectedCueId()}"]`)?.click());
        const heading = document.querySelector("#detail h2");
        if (heading) heading.textContent = "Every cue carries its own review boundary.";
      }
    }
    const selectedClaim = summary.claims.find((claim) => claim.cue_id === selectedCueId());
    const signoff = document.querySelector("#signoffRecipes");
    if (signoff && selectedClaim?.current && summary.staleClaims.length) {
      signoff.id = "nextStaleClaim";
      signoff.textContent = "Open next stale claim";
      signoff.addEventListener("click", () => {
        const next = summary.staleClaims[0];
        document.querySelector(`[data-inspect="${next.cue_id}"]`)?.click();
      });
    }
  }

  function enhance() {
    if (!currentProject) return;
    const workspace = document.querySelector("#workspace");
    const activeStep = document.querySelector(".steps button.active")?.dataset.step || "script";
    const marker = `${currentProject.id}:${currentProject.revision}:${activeStep}:${selectedCueId()}`;
    if (workspace?.dataset.cockpitMarker === marker) return;
    if (workspace) workspace.dataset.cockpitMarker = marker;
    const summary = workflow();
    const title = document.querySelector("#projectTitle");
    if (title) title.textContent = currentProject.title;
    const paperEdit = document.querySelector("#script-heading");
    if (paperEdit) paperEdit.textContent = currentProject.title === "Apollo 11 paper edit" ? "Apollo 11 paper edit" : "Imported paper edit";
    const policy = document.querySelector("#fingerprint");
    if (policy) policy.textContent = "Policy cutline-review-v1";
    renderMetrics(summary);
    renderLedger();
    enhanceSources();
    enhanceIntegrations(summary);
    enhanceImpact(summary);
    repairCustomActions(summary);
  }

  async function refreshProjects() {
    try {
      const response = await nativeFetch("/api/project-summaries", { credentials: "same-origin" });
      if (!response.ok) return;
      const projects = (await response.json()).projects || [];
      const button = document.querySelector("#resumeProject");
      if (!button) return;
      if (projects.length) {
        latestProjectId = projects[0].id;
        button.hidden = false;
        button.textContent = `Resume “${projects[0].title}” · Revision ${projects[0].revision}`;
      } else {
        latestProjectId = null;
        button.hidden = true;
      }
    } catch {
      // Resume is progressive enhancement; the core demo remains available.
    }
  }

  function createCustomProject(event) {
    event.preventDefault();
    const title = document.querySelector("#customTitle").value.trim();
    const lines = document.querySelector("#customScript").value.split(/\r?\n/)
      .map((line) => line.trim()).filter(Boolean);
    if (!title || !lines.length || lines.length > 12) {
      showToast("Enter a title and between 1 and 12 narration cues.");
      return;
    }
    pendingCreate = {
      title,
      cues: lines.map((text, index) => ({
        text,
        start_ms: index * 5_000,
        end_ms: index * 5_000 + 4_500,
        kind: "NARRATION_DRAFT",
      })),
    };
    document.querySelector("#importDialog").close();
    document.querySelector("#start").click();
  }

  async function copyAudit() {
    if (!currentProject) return;
    const summary = workflow();
    const text = [
      "CUTLINE review audit",
      `Project: ${currentProject.title}`,
      `Revision: ${currentProject.revision}`,
      "Policy: cutline-review-v1",
      `Current claims: ${summary.currentClaims.length}/${summary.claims.length}`,
      `Current recipes: ${summary.currentRecipes.length}/${summary.recipes.length}`,
      `Evidence captures: ${summary.sources}`,
      `Audit events: ${(currentProject.events || []).length}`,
    ].join("\n");
    try {
      await navigator.clipboard.writeText(text);
      showToast("Audit summary copied.");
    } catch {
      showToast("Clipboard access is unavailable in this browser.");
    }
  }

  window.addEventListener("DOMContentLoaded", () => {
    document.querySelector("#openArchitecture")?.addEventListener("click", () => document.querySelector("#architectureDialog").showModal());
    document.querySelector("#openImport")?.addEventListener("click", () => document.querySelector("#importDialog").showModal());
    document.querySelector("#newReview")?.addEventListener("click", () => document.querySelector("#importDialog").showModal());
    document.querySelector("#cancelImport")?.addEventListener("click", () => document.querySelector("#importDialog").close());
    document.querySelector("#importForm")?.addEventListener("submit", createCustomProject);
    document.querySelector("#copyAudit")?.addEventListener("click", copyAudit);
    document.querySelector("#resumeProject")?.addEventListener("click", () => {
      if (!latestProjectId) return;
      pendingResume = latestProjectId;
      document.querySelector("#start").click();
    });
    const observer = new MutationObserver(queueEnhance);
    observer.observe(document.querySelector("#workspace"), { childList: true, subtree: true });
    if (capabilities) refreshProjects();
  });
})();
