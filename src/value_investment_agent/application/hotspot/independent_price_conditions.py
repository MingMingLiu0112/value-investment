"""Versioned successor view; never rewrite legacy observation cases or packets."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .current_registry import load_price_conditions
from .independent_admission import load_independent_admission


def project_independent_price_condition(root: Path, *, symbol: str, plan: dict,
        now: datetime, allow_test_only: bool = False) -> dict:
    """Read-only projection of a caller-verified current plan; preserve its bytes.

    This helper does not verify a client-supplied plan. Callers must obtain it
    from the existing case/registry verifier before invoking this projection.
    Synthetic releases require explicit isolated opt-in, never a plan field.
    """
    if (not isinstance(plan, dict)
            or plan.get("schema_version") != "price-action-plan-current-v1"
            or plan.get("symbol") != symbol or plan.get("action") != "no_order"):
        raise ValueError("Independent projection requires a matching current no-order plan")
    if type(allow_test_only) is not bool:
        raise ValueError("Test-only permission requires an explicit boolean")
    output = deepcopy(plan)
    # The successor has independent admission; retain legacy wording only in
    # immutable source cases, not in the user's current conditional plan.
    open_rule = (
        "完整60分钟收盘价严格高于前五根最高价，且成交量至少为前五根均量的1.2倍；"
        "仅在无持仓且热点独立策略、证券与事件、时点、验证及个人风险门禁全部通过后，"
        "进入人工开仓复核。"
    )
    if isinstance(output.get("entry_condition"), dict):
        output["entry_condition"]["rule"] = open_rule
    if isinstance(output.get("conditional_action_rules", {}).get("OPEN"), dict):
        output["conditional_action_rules"]["OPEN"]["rule"] = open_rule
    try:
        admission = load_independent_admission(root, symbol=symbol, now=now,
            allow_test_only=allow_test_only)
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
    quality = plan.get("opportunity_quality")
    if (not isinstance(quality, dict)
            or quality.get("structure_tier") != "STRUCTURE_QUALIFIED_OBSERVATION"):
        blockers.append("CURRENT_STRUCTURE_NOT_QUALIFIED")
    if plan.get("signal_state") != "TRIGGER_OBSERVED":
        blockers.append("CURRENT_ENTRY_CONDITION_NOT_OBSERVED")
    if plan.get("candidate_lifecycle") == "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY":
        blockers.append("NOT_IN_CURRENT_CANDIDATE_POOL")
    if plan.get("observation_scope") == "LAST_COMPLETED_CLOSE_DISPLAY_ONLY":
        blockers.append("DISPLAY_ONLY_EVIDENCE_NOT_CURRENT_ADMISSION")
    output.update(schema_version="price-action-plan-independent-v2",
        legacy_observation_blockers=deepcopy(plan.get("blockers", [])),
        independent_admission=admission, blockers=list(dict.fromkeys(blockers)),
        risk_review_eligible=admission["risk_review_eligible"] is True and not blockers,
        formal_eligibility=False, action_eligibility=False, portfolio_eligibility=None,
        position_guidance=None, trade_eligible=False, action="no_order")
    return output


def load_independent_price_conditions(root: Path, *, now: datetime,
        research_version: str | None, allow_test_only: bool = False) -> dict:
    legacy = load_price_conditions(root, now=now, research_version=research_version)
    output = deepcopy(legacy)
    output.update(schema_version="independent-hotspot-price-conditions-v1", action="no_order")
    for item in output.get("items", []):
        item["price_action_plan"] = project_independent_price_condition(root,
            symbol=item["symbol"], plan=item["price_action_plan"], now=now,
            allow_test_only=allow_test_only)
    return output
