from __future__ import annotations

from copy import deepcopy
from typing import Any

from cutline.domain import DomainError, Project, canonical, new_project, snapshot


def new_custom_project(
    owner_hash: str,
    mode: str,
    ttl_hours: int,
    title: str,
    cue_specs: list[dict[str, Any]],
) -> Project:
    clean_title = canonical(title).strip()
    if not clean_title or len(clean_title) > 120:
        raise DomainError("INVALID_PROJECT", "Project title must contain 1–120 characters.", 422)
    if not 1 <= len(cue_specs) <= 12:
        raise DomainError("INVALID_PROJECT", "A project must contain 1–12 cues.", 422)

    project = new_project(owner_hash, mode, ttl_hours)
    cues: dict[str, dict[str, Any]] = {}
    claims: dict[str, dict[str, Any]] = {}
    claim_number = 1
    previous_end = -1
    for cue_number, spec in enumerate(cue_specs, start=1):
        cue_id = f"c{cue_number}"
        kind = str(spec.get("kind", "NARRATION_DRAFT"))
        text = canonical(str(spec.get("text", ""))).strip()
        start_ms = int(spec.get("start_ms", -1))
        end_ms = int(spec.get("end_ms", -1))
        if kind not in {"NARRATION_DRAFT", "QUOTATION"}:
            raise DomainError("INVALID_PROJECT", "Cue kind is invalid.", 422)
        if not 1 <= len(text) <= 500 or start_ms < 0 or end_ms <= start_ms:
            raise DomainError("INVALID_PROJECT", "Cue text or time range is invalid.", 422)
        if start_ms < previous_end:
            raise DomainError("INVALID_PROJECT", "Cue time ranges cannot overlap.", 422)
        previous_end = end_ms
        cues[cue_id] = {
            "id": cue_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "original_text": text,
            "text": text,
            "kind": kind,
            "content_revision": 1,
            "coverage": "ANNOTATION_ONLY" if kind == "QUOTATION" else "PENDING_REVIEW",
        }
        if kind == "NARRATION_DRAFT":
            claim_id = f"k{claim_number}"
            claims[claim_id] = {
                "id": claim_id,
                "cue_id": cue_id,
                "span": text.rstrip("."),
                "proposition": text,
                "assessment": "UNASSESSED",
                "rationale": "",
                "source_ids": [],
                "research_hash": "",
                "review_hash": "",
                "proposal": None,
                "provider_receipt": None,
            }
            claim_number += 1
    if not claims:
        raise DomainError("INVALID_PROJECT", "At least one narration cue is required.", 422)

    project["title"] = clean_title
    project["cues"] = cues
    project["sources"] = {}
    project["claims"] = claims
    project["recipes"] = {
        "main": {
            "id": "main",
            "name": "Main cut",
            "cue_ids": list(cues),
            "signoff_hash": "",
        }
    }
    event = deepcopy(project["events"][0])
    event.update({"template": "CUSTOM_SCRIPT", "cue_count": len(cues)})
    project["events"] = [event]
    return project


def project_summary(project: Project) -> dict[str, Any]:
    state = snapshot(project)
    return {
        "id": state["id"],
        "title": state["title"],
        "mode": state["mode"],
        "revision": state["revision"],
        "created_at": state["created_at"],
        "updated_at": state["updated_at"],
        "expires_at": state["expires_at"],
        "stale_claim_ids": state["stale_claim_ids"],
        "recipe_count": len(state["recipes"]),
        "current_recipe_count": sum(1 for recipe in state["recipes"].values() if recipe["current"]),
    }
