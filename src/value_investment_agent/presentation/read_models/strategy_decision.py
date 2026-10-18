"""Public display envelope over existing plans; never an admission verifier."""
from __future__ import annotations

from copy import deepcopy
import re


SCHEMA = "strategy-decision-read-model-v1"
_STRATEGIES = {
    "value-action-plan-v1": "CORE_VALUE",
    "price-action-plan-current-v1": "HOTSPOT_SATELLITE",
    "price-action-plan-independent-v2": "HOTSPOT_SATELLITE",
}
_CONDITION_FIELDS = frozenset({
    "kind", "price", "comparison", "scenario", "scenario_value", "value_fraction",
    "rationale", "triggered", "rule_version", "policy_id", "qualification",
    "intent", "observed", "rule", "requires_existing_holding", "status",
    "formal_eligibility", "personal_permission", "action", "reasons",
    "thesis_review", "entry_id", "consistency_status",
})


def _condition(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Plan condition must be an object or absent")
    if "action" in value and value["action"] != "no_order":
        raise ValueError("Condition cannot authorize orders")
    result = {}
    for key in _CONDITION_FIELDS & value.keys():
        item = value[key]
        if key == "thesis_review":
            result[key] = _condition(item)
        elif key in {"formal_eligibility", "personal_permission"}:
            result[key] = False
        elif key == "reasons":
            result[key] = [text for text in item if isinstance(text, str)] if isinstance(item, list) else []
        elif item is None or isinstance(item, (str, bool, int, float)):
            result[key] = deepcopy(item)
    return result


def _fields(plan, names):
    return {name: deepcopy(plan[name]) for name in names
            if isinstance(plan.get(name), (str, bool, int, float))}


def project_strategy_decision(plan: dict, *, symbol: str | None = None) -> dict:
    """Project an already public plan without copying private account extensions.

    Input flags and review labels are not cryptographic proof. This envelope
    deliberately grants no formal or personal eligibility, including for v2.
    """
    if not isinstance(plan, dict) or plan.get("schema_version") not in _STRATEGIES:
        raise ValueError("Unsupported strategy plan schema")
    strategy = _STRATEGIES[plan["schema_version"]]
    identity = plan.get("symbol")
    if (not isinstance(identity, str) or re.fullmatch(r"[0-9]{6}", identity) is None
            or (symbol is not None and symbol != identity)):
        raise ValueError("Plan security identity mismatch")
    if (plan.get("action") != "no_order" or plan.get("strategy") != strategy
            or plan.get("sleeve", strategy) != strategy):
        raise ValueError("Plan strategy or action mismatch")
    value = strategy == "CORE_VALUE"
    basis = _fields(plan, (
        "research_version", "research_as_of", "valuation_date", "valuation_input_version",
        "model_id", "model_type", "model_version", "profile_id", "bear", "base", "bull",
    ) if value else (
        "research_version", "case_sha256", "primary_timeframe", "trend_state",
        "reference_price_scope", "valid_from_session", "expires_after_session",
    ))
    evidence = []
    for ref in plan.get("evidence_refs") or []:
        if isinstance(ref, str) and re.fullmatch(r"[0-9a-f]{64}", ref):
            evidence.append(ref)
        elif isinstance(ref, dict) and re.fullmatch(r"[0-9a-f]{64}", str(ref.get("sha256", ""))):
            evidence.append({"sha256": ref["sha256"]})
    invalidation = plan.get("invalidation_condition")
    if value:
        reasons = plan.get("thesis_invalidation")
        invalidation = {"kind": "THESIS_INVALIDATION", "reasons": reasons} if isinstance(reasons, list) else None
    admission = plan.get("independent_admission")
    review = (admission.get("review_status") if isinstance(admission, dict)
              and plan["schema_version"] == "price-action-plan-independent-v2" else None)
    return {
        "schema_version": SCHEMA, "source_schema_version": plan["schema_version"],
        "strategy": strategy, "symbol": identity,
        "as_of": plan.get("decision_as_of" if value else "market_trade_date")
        if isinstance(plan.get("decision_as_of" if value else "market_trade_date"), str) else None,
        "data_available_at": plan.get("data_available_at") if isinstance(plan.get("data_available_at"), str) else None,
        "research_or_structure_basis": basis,
        "condition_type": "VALUE_POLICY_OR_THESIS_REVIEW" if value else "PRICE_STRUCTURE_REVIEW",
        "entry_condition": _condition(plan.get("entry_condition")),
        "exit_condition": _condition(plan.get("exit_condition")),
        "invalidation_condition": _condition(invalidation),
        "risk_basis": _fields(plan, ("qualification",) if value else ("risk_reward_ratio", "invalidation_price")),
        "review_status": review if isinstance(review, str) else "UNKNOWN",
        "personal_risk_status": "UNKNOWN_PRIVATE_INPUT_NOT_PROJECTED",
        "evidence_refs": evidence,
        "rule_version": plan.get("model_or_rule_version") if isinstance(plan.get("model_or_rule_version"), str) else None,
        "formal_eligibility": False, "portfolio_eligibility": None,
        "action": "no_order",
    }
