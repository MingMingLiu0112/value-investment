"""Versioned successor view; never rewrite legacy observation cases or packets."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .current_registry import load_price_conditions
from .independent_admission import load_independent_admission


def load_independent_price_conditions(root: Path, *, now: datetime,
        research_version: str | None) -> dict:
    legacy = load_price_conditions(root, now=now, research_version=research_version)
    output = deepcopy(legacy)
    output.update(schema_version="independent-hotspot-price-conditions-v1", action="no_order")
    for item in output.get("items", []):
        plan = item["price_action_plan"]
        try:
            admission = load_independent_admission(root, symbol=item["symbol"], now=now)
        except (ValueError, OSError, KeyError, TypeError):
            admission = {"status": "OBSERVATION_ONLY", "risk_review_eligible": False,
                "review_status": "REJECTED", "blockers": ["INDEPENDENT_RELEASE_INVALID"],
                "action": "no_order"}
        blockers = list(admission["blockers"])
        if admission.get("rule_version") != plan.get("model_or_rule_version"):
            blockers.append("STRATEGY_RULE_VERSION_MISMATCH")
        case_binding = {"path": plan.get("case_path"), "sha256": plan.get("case_sha256")}
        if case_binding not in admission.get("gate_source_bindings", {}).get("price_structure", []):
            blockers.append("CURRENT_CASE_NOT_BOUND_TO_STRATEGY_RELEASE")
        if plan.get("opportunity_quality", {}).get("structure_tier") != "STRUCTURE_QUALIFIED_OBSERVATION":
            blockers.append("CURRENT_STRUCTURE_NOT_QUALIFIED")
        if plan.get("signal_state") != "TRIGGER_OBSERVED":
            blockers.append("CURRENT_ENTRY_CONDITION_NOT_OBSERVED")
        if plan.get("candidate_lifecycle") == "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY":
            blockers.append("NOT_IN_CURRENT_CANDIDATE_POOL")
        if plan.get("observation_scope") == "LAST_COMPLETED_CLOSE_DISPLAY_ONLY":
            blockers.append("DISPLAY_ONLY_EVIDENCE_NOT_CURRENT_ADMISSION")
        plan.update(schema_version="price-action-plan-independent-v2",
            legacy_observation_blockers=deepcopy(plan.get("blockers", [])),
            independent_admission=admission, blockers=list(dict.fromkeys(blockers)),
            risk_review_eligible=admission["risk_review_eligible"] and not blockers,
            formal_eligibility=False, action_eligibility=False, portfolio_eligibility=None,
            position_guidance=None, trade_eligible=False, action="no_order")
    return output
