"""Explain the already verified decision without granting new authority."""
from copy import deepcopy
import hashlib
import json


def project_decision_logic(plan, *, outcome, blockers, entry_context=None):
    """Only project source-backed plan content; absent research stays absent."""
    context = entry_context or {}
    entries = context.get('entry_contexts') or ([context] if context.get('entry_thesis') is not None else [])
    original = [dict(entry_id=part['entry_thesis'].entry_id, thesis=part['entry_thesis'].thesis,
        consistency_status=getattr(part.get('investment_consistency_review'), 'status', None))
        for part in entries]
    analysis = plan.get("research_analysis") or {}
    fields = {
        "thesis": plan.get("thesis"),
        "return_driver": analysis.get("return_driver"),
        "supporting_evidence": plan.get("supporting_facts"),
        "counter_evidence": plan.get("counter_evidence"),
        "thesis_breakers": plan.get("thesis_invalidation"),
        "next_review": plan.get("next_observation"),
        "original_thesis": original or context.get("original_thesis"),
        "consistency_status": context.get("consistency_status"),
    }
    sources = deepcopy(plan.get("source_bindings") or [])
    # A projection is not an evidence validator or a second eligibility gate.
    # Unbound prose must never acquire a verified label in the account surface.
    bound = bool(sources) and all(isinstance(row, dict)
        and isinstance(row.get("path"), str) and row["path"]
        and isinstance(row.get("sha256"), str) and len(row["sha256"]) == 64
        and all(char in "0123456789abcdef" for char in row["sha256"])
        for row in sources)
    card = {
        "schema_version": "decision-logic-projection-v1", "action": "no_order",
        "scope": "CURRENT_REVERIFIED_PLAN_PROJECTION_NOT_NEW_RESEARCH",
        "decision_action": outcome, "symbol": plan.get("symbol"),
        "research_as_of": plan.get("research_as_of"),
        "research_version": plan.get("research_version", plan.get("valuation_input_version")),
        "source_bindings": sources if bound else [],
        "evidence_refs": deepcopy(plan.get("evidence_refs") or []) if bound else [],
        "valuation": {key: plan.get(key) for key in ("bear", "base", "bull")},
        "confidence": (plan.get("scenario_validity") or {}).get("confidence"),
        "blockers": list(blockers), "broker_execution_permission": False,
        "source_status": "BOUND_TO_REVERIFIED_PLAN" if bound else "NOT_SOURCE_BOUND",
        **{key: deepcopy(value) if bound else None for key, value in fields.items()},
    }
    card["content_sha256"] = hashlib.sha256(json.dumps(card, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return card
