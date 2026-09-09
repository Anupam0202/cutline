from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import secrets
import unicodedata
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

Project = dict[str, Any]
Mutation = Callable[[Project], None]
POLICY_VERSION = "cutline-review-v1"
DEMO_SOURCE_URL = "https://www.nasa.gov/missions/apollo/apollo-11-mission-overview/"


class DomainError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def canonical(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def digest(value: Any) -> str:
    if isinstance(value, str):
        raw = canonical(value)
    else:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC)


def _cue_fingerprint(cue: dict[str, Any]) -> str:
    return digest(
        {
            "id": cue["id"],
            "text": cue["text"],
            "content_revision": cue["content_revision"],
            "kind": cue["kind"],
            "start_ms": cue["start_ms"],
            "end_ms": cue["end_ms"],
        }
    )


def _source_fingerprint(source: dict[str, Any]) -> str:
    return digest(
        {
            "url": source["url"],
            "title": source["title"],
            "capture": source["capture"],
            "retrieved_at": source["retrieved_at"],
        }
    )


def _claim_fingerprint(project: Project, claim: dict[str, Any]) -> str:
    cue = project["cues"][claim["cue_id"]]
    source_fingerprints = [
        _source_fingerprint(project["sources"][source_id])
        for source_id in claim.get("source_ids", [])
        if source_id in project["sources"]
    ]
    return digest(
        {
            "span": claim["span"],
            "proposition": claim["proposition"],
            "assessment": claim["assessment"],
            "rationale": claim.get("rationale", ""),
            "cue": _cue_fingerprint(cue),
            "sources": source_fingerprints,
            "policy": POLICY_VERSION,
        }
    )


def _recipe_fingerprint(project: Project, recipe: dict[str, Any]) -> str:
    return digest(
        {
            "project_title": project["title"],
            "recipe": {
                "id": recipe["id"],
                "name": recipe["name"],
                "cue_ids": recipe["cue_ids"],
            },
            "cues": [
                {
                    "id": cue_id,
                    "fingerprint": _cue_fingerprint(project["cues"][cue_id]),
                    "coverage": project["cues"][cue_id]["coverage"],
                }
                for cue_id in recipe["cue_ids"]
            ],
            "policy": POLICY_VERSION,
        }
    )


def _claims_for_recipe(project: Project, recipe: dict[str, Any]) -> list[dict[str, Any]]:
    cue_ids = set(recipe["cue_ids"])
    return [claim for claim in project["claims"].values() if claim["cue_id"] in cue_ids]


def _claim_is_current(project: Project, claim: dict[str, Any]) -> bool:
    fingerprint = _claim_fingerprint(project, claim)
    return bool(claim.get("review_hash")) and hmac.compare_digest(claim["review_hash"], fingerprint)


def _recipe_is_current(project: Project, recipe: dict[str, Any]) -> bool:
    claims = _claims_for_recipe(project, recipe)
    evidence_current = all(_claim_is_current(project, claim) for claim in claims)
    recipe_current = bool(recipe.get("signoff_hash")) and hmac.compare_digest(
        recipe["signoff_hash"], _recipe_fingerprint(project, recipe)
    )
    return evidence_current and recipe_current


def _append_event(project: Project, event_type: str, **metadata: Any) -> None:
    project["events"].append(
        {
            "type": event_type,
            "at": utc_now().isoformat(),
            **metadata,
        }
    )
    project["events"] = project["events"][-100:]


def new_project(owner_hash: str, mode: str, ttl_hours: int) -> Project:
    now = utc_now()
    cues = {
        "c1": {
            "id": "c1",
            "start_ms": 0,
            "end_ms": 4_300,
            "original_text": "Apollo 11 launched from Earth on July 16, 1969.",
            "text": "Apollo 11 launched from Earth on July 16, 1969.",
            "kind": "NARRATION_DRAFT",
            "content_revision": 1,
            "coverage": "REVIEWED",
        },
        "c2": {
            "id": "c2",
            "start_ms": 4_300,
            "end_ms": 8_500,
            "original_text": "The lunar module landed on the Moon on July 20, 1969.",
            "text": "The lunar module landed on the Moon on July 20, 1969.",
            "kind": "NARRATION_DRAFT",
            "content_revision": 1,
            "coverage": "REVIEWED",
        },
        "q1": {
            "id": "q1",
            "start_ms": 8_500,
            "end_ms": 11_000,
            "original_text": "That's one small step for man.",
            "text": "That's one small step for man.",
            "kind": "QUOTATION",
            "content_revision": 1,
            "coverage": "ANNOTATION_ONLY",
        },
    }
    source = {
        "id": "seed-apollo-11",
        "url": DEMO_SOURCE_URL,
        "title": "Apollo 11 Mission Overview",
        "capture": "Launch July 16, 1969. Lunar landing July 20, 1969.",
        "retrieved_at": "Curated sample capture",
        "provider": "CURATED_SAMPLE",
    }
    claims = {
        "k1": {
            "id": "k1",
            "cue_id": "c1",
            "span": "launched from Earth on July 16, 1969",
            "proposition": "Apollo 11 launched on July 16, 1969.",
            "assessment": "SUPPORTED_DEMO",
            "rationale": "The curated sample capture states the launch date.",
            "source_ids": [source["id"]],
            "research_hash": "",
            "review_hash": "",
            "proposal": None,
            "provider_receipt": {"kind": "CURATED_SAMPLE"},
        },
        "k2": {
            "id": "k2",
            "cue_id": "c2",
            "span": "landed on the Moon on July 20, 1969",
            "proposition": "The Apollo 11 lunar module landed on July 20, 1969.",
            "assessment": "SUPPORTED_DEMO",
            "rationale": "The curated sample capture states the lunar landing date.",
            "source_ids": [source["id"]],
            "research_hash": "",
            "review_hash": "",
            "proposal": None,
            "provider_receipt": {"kind": "CURATED_SAMPLE"},
        },
    }
    project: Project = {
        "id": secrets.token_urlsafe(12),
        "owner_hash": owner_hash,
        "title": "Apollo 11 paper edit",
        "mode": mode.upper(),
        "revision": 1,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "expires_at": now + timedelta(hours=ttl_hours),
        "cues": cues,
        "sources": {source["id"]: source},
        "claims": claims,
        "recipes": {
            "main": {"id": "main", "name": "Main cut", "cue_ids": ["c1", "c2", "q1"], "signoff_hash": ""},
            "teaser": {"id": "teaser", "name": "Teaser", "cue_ids": ["c1", "q1"], "signoff_hash": ""},
            "control": {
                "id": "control",
                "name": "Independent control",
                "cue_ids": ["c2"],
                "signoff_hash": "",
            },
        },
        "events": [],
    }
    for claim in claims.values():
        fingerprint = _claim_fingerprint(project, claim)
        claim["research_hash"] = fingerprint
        claim["review_hash"] = fingerprint
    for recipe in project["recipes"].values():
        recipe["signoff_hash"] = _recipe_fingerprint(project, recipe)
    _append_event(project, "PROJECT_CREATED", mode=mode.upper())
    return project


def snapshot(project: Project) -> Project:
    result = deepcopy(project)
    stale_claim_ids: list[str] = []
    for claim in result["claims"].values():
        claim["current"] = _claim_is_current(result, claim)
        claim["evidence_current"] = bool(claim.get("research_hash")) and hmac.compare_digest(
            claim["research_hash"], _claim_fingerprint(result, claim)
        )
        if not claim["current"]:
            stale_claim_ids.append(claim["id"])
    for recipe in result["recipes"].values():
        recipe["current"] = _recipe_is_current(result, recipe)
    result["stale_claim_ids"] = stale_claim_ids
    result["expires_at"] = (
        result["expires_at"].isoformat()
        if isinstance(result["expires_at"], datetime)
        else result["expires_at"]
    )
    result.pop("owner_hash", None)
    return result


def edit_cue(project: Project, cue_id: str, text: str) -> None:
    cue = project["cues"].get(cue_id)
    if cue is None:
        raise DomainError("NOT_FOUND", "Cue not found.", 404)
    if cue["kind"] == "QUOTATION":
        raise DomainError(
            "QUOTATION_IMMUTABLE",
            "Quoted material is immutable; add separately attributed narration instead.",
            403,
        )
    normalized = canonical(text).strip()
    if not 1 <= len(normalized) <= 500:
        raise DomainError("INVALID_CUE", "Cue text must contain 1–500 characters.", 422)
    if normalized == cue["text"]:
        return
    cue["text"] = normalized
    cue["content_revision"] += 1
    for claim in project["claims"].values():
        if claim["cue_id"] == cue_id:
            claim.update(
                {
                    "span": normalized.rstrip("."),
                    "proposition": normalized,
                    "assessment": "UNASSESSED",
                    "rationale": "",
                    "source_ids": [],
                    "research_hash": "",
                    "review_hash": "",
                    "proposal": None,
                    "provider_receipt": None,
                }
            )
    _append_event(project, "CUE_EDITED", cue_id=cue_id)


def apply_research(project: Project, cue_id: str, outcome: dict[str, Any]) -> None:
    claim = next((item for item in project["claims"].values() if item["cue_id"] == cue_id), None)
    if claim is None:
        raise DomainError("NOT_FOUND", "Claim not found.", 404)
    source_ids: list[str] = []
    for source in outcome["sources"]:
        source_id = f"source-{digest(source)[:16]}"
        clean_source = {
            "id": source_id,
            "url": source["url"],
            "title": source["title"],
            "capture": source["capture"],
            "retrieved_at": source["retrieved_at"],
            "provider": source.get("provider", "PARALLEL_SEARCH"),
        }
        project["sources"][source_id] = clean_source
        source_ids.append(source_id)
    claim.update(
        {
            "span": outcome["span"],
            "proposition": outcome["proposition"],
            "assessment": outcome["assessment"],
            "rationale": outcome["rationale"],
            "source_ids": source_ids,
            "proposal": outcome.get("proposal"),
            "provider_receipt": outcome["provider_receipt"],
            "review_hash": "",
        }
    )
    claim["research_hash"] = _claim_fingerprint(project, claim)
    _append_event(
        project,
        "RESEARCH_COMPLETED",
        cue_id=cue_id,
        assessment=claim["assessment"],
        source_count=len(source_ids),
    )


def review_claim(project: Project, cue_id: str) -> None:
    claim = next((item for item in project["claims"].values() if item["cue_id"] == cue_id), None)
    if claim is None:
        raise DomainError("NOT_FOUND", "Claim not found.", 404)
    fingerprint = _claim_fingerprint(project, claim)
    if not claim.get("research_hash") or not hmac.compare_digest(claim["research_hash"], fingerprint):
        raise DomainError("STALE_EVIDENCE", "Research this exact cue revision before review.", 409)
    if claim["assessment"] not in {"SUPPORTED", "SUPPORTED_DEMO"}:
        raise DomainError("INSUFFICIENT_SUPPORT", "Only supported wording can be approved.", 409)
    claim["review_hash"] = fingerprint
    _append_event(project, "CLAIM_APPROVED", cue_id=cue_id)


def apply_proposal(project: Project, cue_id: str, confirmed: bool) -> None:
    if not confirmed:
        raise DomainError(
            "CONFIRMATION_REQUIRED",
            "Explicit confirmation is required before changing narration.",
            422,
        )
    claim = next((item for item in project["claims"].values() if item["cue_id"] == cue_id), None)
    if claim is None:
        raise DomainError("NOT_FOUND", "Claim not found.", 404)
    proposal = claim.get("proposal")
    if not proposal or not proposal.get("new_text"):
        raise DomainError("NO_PROPOSAL", "No supported repair is available.", 409)
    cue = project["cues"][cue_id]
    cue["text"] = canonical(proposal["new_text"]).strip()
    cue["content_revision"] += 1
    claim.update(
        {
            "span": cue["text"].rstrip("."),
            "proposition": cue["text"],
            "assessment": "UNASSESSED",
            "rationale": "",
            "source_ids": [],
            "research_hash": "",
            "review_hash": "",
            "proposal": None,
            "provider_receipt": None,
        }
    )
    _append_event(project, "PROPOSAL_APPLIED", cue_id=cue_id, requires_rerecording=True)


def signoff_recipes(project: Project) -> None:
    signed = 0
    for recipe in project["recipes"].values():
        claims = _claims_for_recipe(project, recipe)
        if all(_claim_is_current(project, claim) for claim in claims):
            recipe["signoff_hash"] = _recipe_fingerprint(project, recipe)
            signed += 1
    if not signed:
        raise DomainError("STALE_REVIEW", "Resolve stale claim reviews before signoff.", 409)
    _append_event(project, "RECIPES_SIGNED_OFF", count=signed)


def commit_mutation(project: Project, mutation: Mutation) -> Project:
    mutation(project)
    project["revision"] += 1
    project["updated_at"] = utc_now().isoformat()
    return project


def export_handoff(project: Project, recipe_id: str = "main") -> dict[str, Any]:
    recipe = project["recipes"].get(recipe_id)
    if recipe is None:
        raise DomainError("NOT_FOUND", "Recipe not found.", 404)
    if not _recipe_is_current(project, recipe):
        raise DomainError(
            "STALE_REVIEW",
            "Export is blocked until claim review and recipe signoff are current.",
            409,
        )
    cues = []
    for cue_id in recipe["cue_ids"]:
        cue = deepcopy(project["cues"][cue_id])
        cue["before_text"] = cue["original_text"]
        cue["after_text"] = cue["text"]
        cue["changed"] = cue["original_text"] != cue["text"]
        cue["requires_rerecording"] = cue["changed"] and cue["kind"] == "NARRATION_DRAFT"
        cues.append(cue)
    claim_ids = {claim["id"] for claim in project["claims"].values() if claim["cue_id"] in recipe["cue_ids"]}
    claims = [deepcopy(claim) for claim in project["claims"].values() if claim["id"] in claim_ids]
    source_ids = {source_id for claim in claims for source_id in claim.get("source_ids", [])}
    review_scope = (
        "Exact cue wording, revisions, timecodes, source captures, assessments, approvals, and recipe order."
    )
    disclaimer = (
        "Editorial review support only; not a truth certificate, legal clearance, or audiovisual edit."
    )
    return {
        "artifact": "CUTLINE editorial handoff",
        "project_id": project["id"],
        "recipe": recipe["name"],
        "mode": project["mode"],
        "revision": project["revision"],
        "review_scope": review_scope,
        "disclaimer": disclaimer,
        "cues": cues,
        "claims": claims,
        "sources": [deepcopy(project["sources"][source_id]) for source_id in sorted(source_ids)],
    }


def csv_safe(value: Any) -> str:
    text = str(value if value is not None else "")
    if text.lstrip(" \t\r\n\ufeff")[:1] in {"=", "+", "-", "@"}:
        return "'" + text
    return text


def export_csv(data: dict[str, Any]) -> str:
    fields = [
        "cue_id",
        "start_ms",
        "end_ms",
        "kind",
        "before_text",
        "after_text",
        "changed",
        "requires_rerecording",
        "review_scope",
        "disclaimer",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for cue in data["cues"]:
        row = {
            "cue_id": cue["id"],
            "start_ms": cue["start_ms"],
            "end_ms": cue["end_ms"],
            "kind": cue["kind"],
            "before_text": cue["before_text"],
            "after_text": cue["after_text"],
            "changed": str(cue["changed"]).lower(),
            "requires_rerecording": str(cue["requires_rerecording"]).lower(),
            "review_scope": data["review_scope"],
            "disclaimer": data["disclaimer"],
        }
        writer.writerow({key: csv_safe(value) for key, value in row.items()})
    return output.getvalue()


def export_text(data: dict[str, Any]) -> str:
    lines = [
        data["artifact"],
        f"Recipe: {data['recipe']}",
        f"Mode: {data['mode']}",
        f"Revision: {data['revision']}",
        f"Scope: {data['review_scope']}",
        f"Disclaimer: {data['disclaimer']}",
        "",
    ]
    for cue in data["cues"]:
        lines.extend(
            [
                f"[{cue['start_ms']}–{cue['end_ms']} ms] {cue['kind']} {cue['id']}",
                f"Before: {cue['before_text']}",
                f"After: {cue['after_text']}",
                f"Re-record: {'yes' if cue['requires_rerecording'] else 'no'}",
                "",
            ]
        )
    for source in data["sources"]:
        lines.extend(
            [
                f"Source: {source['title']}",
                f"URL: {source['url']}",
                f"Capture: {source['capture']}",
                f"Retrieved: {source['retrieved_at']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
