"""Versioned successor view; never rewrite legacy observation cases or packets."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .current_registry import load_price_conditions
from .independent_admission import load_independent_admission
from .current_case_review import suppress_current_price_conditions
from .replay_read_model import load_current_hotspot_validation

INDEPENDENT_OPEN_RULE = (
    "完整60分钟收盘价严格高于前五根最高价，且成交量至少为前五根均量的1.2倍；"
    "仅在无持仓且热点独立策略、证券与事件、时点、验证及个人风险门禁全部通过后，"
    "进入人工开仓复核。"
)


def observed_held_add(plan: dict) -> bool:
    """Inspect the existing producer rule, never establish ownership or admission."""
    add = plan.get("add_condition")
    return (isinstance(add, dict)
        and add == (plan.get("conditional_action_rules") or {}).get("ADD")
        and add.get("intent") == "ADD" and add.get("observed") is True
        and add.get("requires_existing_holding") is True
        and add.get("action") == "no_order"
        and plan.get("signal_state") not in {"STALE", "BLOCKED", "TRIGGER_REJECTED", "EXPIRED"})


def _project_independent_price_condition(root: Path, *, symbol: str, plan: dict,
        now: datetime, allow_test_only: bool = False, review_action: str = "OPEN") -> dict:
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
    if review_action not in {"OPEN", "ADD"}:
        raise ValueError("Unsupported independent review action")
    output = deepcopy(plan)
    # The successor has independent admission; retain legacy wording only in
    # immutable source cases, not in the user's current conditional plan.
    open_rule = INDEPENDENT_OPEN_RULE
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
    # Admission and current-data integrity are separate dimensions. A signed
    # release cannot recover stale data or discard a failed publication check.
    data_blockers = [item for item in plan.get("blockers", []) if item.startswith((
        "CURRENT_", "DISPLAY_ONLY_", "PUBLICATION_"))]
    blockers.extend(data_blockers)
    data_status = ("INVALID" if plan.get("signal_state") == "BLOCKED" else
        "STALE" if plan.get("signal_state") in {"STALE", "EXPIRED"}
        or plan.get("retained_observation_valid") is False else plan.get("current_data_status", "CURRENT"))
    if data_status != "CURRENT":
        blockers.append("CURRENT_MARKET_DATA_STALE" if data_status == "STALE" else "CURRENT_CASE_EVIDENCE_INVALID")
    if admission.get("rule_version") != plan.get("model_or_rule_version"):
        blockers.append("STRATEGY_RULE_VERSION_MISMATCH")
    case_binding = {"path": plan.get("case_path"), "sha256": plan.get("case_sha256")}
    if case_binding not in admission.get("gate_source_bindings", {}).get("price_structure", []):
        blockers.append("CURRENT_CASE_NOT_BOUND_TO_STRATEGY_RELEASE")
    quality = plan.get("opportunity_quality")
    if review_action == "ADD":
        # A recovery does not require another rolling-window OPEN breakout.
        # Keep the same daily/space/conflict safeguards and signed admission.
        behavior = plan.get("price_behavior") or {}
        if (not isinstance(quality, dict) or quality.get("structure_tier") == "CONFLICT_OR_REJECTED"
                or behavior.get("daily_trend") not in {"UPTREND", "RANGE"}
                or behavior.get("observation_quality") != "RESEARCH_ONLY"
                or behavior.get("structural_invalidation") is not False):
            blockers.append("CURRENT_STRUCTURE_NOT_QUALIFIED")
        if not observed_held_add(plan):
            blockers.append("CURRENT_ADD_CONDITION_NOT_CONFIRMED")
    elif (not isinstance(quality, dict)
            or quality.get("structure_tier") != "STRUCTURE_QUALIFIED_OBSERVATION"):
        blockers.append("CURRENT_STRUCTURE_NOT_QUALIFIED")
    if review_action == "OPEN" and plan.get("signal_state") != "TRIGGER_OBSERVED":
        blockers.append("CURRENT_ENTRY_CONDITION_NOT_OBSERVED")
    if plan.get("candidate_lifecycle") == "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY":
        blockers.append("NOT_IN_CURRENT_CANDIDATE_POOL")
    if plan.get("observation_scope") == "LAST_COMPLETED_CLOSE_DISPLAY_ONLY":
        blockers.append("DISPLAY_ONLY_EVIDENCE_NOT_CURRENT_ADMISSION")
    output.update(schema_version="price-action-plan-independent-v2",
        legacy_observation_blockers=deepcopy(plan.get("blockers", [])),
        independent_admission=admission, blockers=list(dict.fromkeys(blockers)),
        current_data_status=data_status,
        risk_review_eligible=admission["risk_review_eligible"] is True and not blockers,
        formal_eligibility=False, action_eligibility=False, portfolio_eligibility=None,
        position_guidance=None, trade_eligible=False, action="no_order")
    if review_action == "ADD":
        output["risk_review_action"] = "ADD"
    if data_status != "CURRENT":
        output = suppress_current_price_conditions(output)
    return output


def _attach_operational_evidence(plan: dict, validation: dict) -> dict:
    """Join verified conditions to sample-specific evidence without new signals."""
    output = deepcopy(plan)
    evidence = deepcopy(validation)
    same_case = any(row.get("symbol") == plan["symbol"]
        and row.get("case_path") == plan.get("case_path")
        and row.get("case_sha256") == plan.get("case_sha256")
        for row in evidence["case_bindings"])
    matching_rule = plan.get("model_or_rule_version") in evidence["rule_versions"]
    evidence["applicability"] = (
        "NO_VERIFIED_VALIDATION" if evidence["source_integrity"] != "VERIFIED" else
        "SAME_CASE_DESCRIPTIVE_ONLY" if same_case and matching_rule else
        "HISTORICAL_OTHER_CASES_NOT_CURRENT_STRUCTURE")
    evidence["current_rule_matches_replayed_rule"] = matching_rule
    if evidence["source_integrity"] == "VERIFIED" and not (same_case and matching_rule):
        evidence["blockers"].append("RETAINED_SAMPLE_DOES_NOT_VALIDATE_CURRENT_CASE")
    output["validation"] = evidence
    current = plan["current_data_status"] == "CURRENT"
    behavior = plan.get("price_behavior") or {}
    quality = plan.get("opportunity_quality") or {}
    levels = plan.get("levels") or {}
    output["operational_conditions"] = dict(
        schema_version="hotspot-operational-conditions-v1",
        status="OBSERVATION_ONLY" if current else "UNAVAILABLE_CURRENT_CONDITIONS",
        case_binding=dict(path=plan.get("case_path"), sha256=plan.get("case_sha256")),
        data_available_at=plan.get("data_available_at"),
        market_trade_date=plan.get("market_trade_date"),
        expires_after_session=plan.get("expires_after_session") if current else None,
        observation_scope=plan.get("observation_scope", plan.get("reference_price_scope")),
        timeframes={period: dict(role=role,
            structure=(plan.get("period_structure") or {}).get(period),
            **deepcopy(levels.get(period, {}))) for period, role in (
                ("daily", "TREND_CONTEXT"), ("60m", "PRIMARY_TRIGGER"),
                ("15m", "AUXILIARY_OBSERVATION_ONLY"))} if current else {},
        conditions=deepcopy(plan.get("conditional_action_rules", {})) if current else {},
        signal_state=plan.get("signal_state"), daily_trend=behavior.get("daily_trend"),
        structure_tier=quality.get("structure_tier"),
        structure_reasons=deepcopy(quality.get("structure_reasons", [])),
        risk_reward_ratio=plan.get("risk_reward_ratio") if current else None,
        risk_reward_scope=behavior.get("risk_reward_scope"),
        execution_checks=deepcopy(behavior.get("execution_checks", [])),
        execution_metrics=deepcopy(evidence["execution_metrics"]),
        validation_evidence_sha256=evidence.get("evidence_sha256"),
        validation_applicability=evidence["applicability"],
        blockers=list(dict.fromkeys([*plan["blockers"], *evidence["blockers"]])),
        holdings_status="UNKNOWN", personal_permission=False, position_guidance=None,
        formal_eligibility=False, action="no_order")
    return output


def project_independent_price_condition(root: Path, *, symbol: str, plan: dict,
        now: datetime, allow_test_only: bool = False, review_action: str = "OPEN") -> dict:
    """Project a caller-verified case with independently reverified validation."""
    output = _project_independent_price_condition(root, symbol=symbol, plan=plan,
        now=now, allow_test_only=allow_test_only, review_action=review_action)
    validation = load_current_hotspot_validation(root=root, now=now)
    return _attach_operational_evidence(output, validation)


def project_independent_price_conditions(root: Path, *, items: list[dict], now: datetime,
        allow_test_only: bool = False) -> dict:
    """Project caller-verified rows with one retained replay for the entire batch."""
    output = dict(schema_version="independent-hotspot-price-conditions-v1",
                  items=deepcopy(items), action="no_order")
    validation = load_current_hotspot_validation(root=root, now=now)
    output["validation"] = deepcopy(validation)
    for item in output.get("items", []):
        plan = _project_independent_price_condition(root,
            symbol=item["symbol"], plan=item["price_action_plan"], now=now,
            allow_test_only=allow_test_only)
        item["price_action_plan"] = _attach_operational_evidence(plan, validation)
    return output


def load_independent_price_conditions(root: Path, *, now: datetime,
        research_version: str | None, allow_test_only: bool = False) -> dict:
    legacy = load_price_conditions(root, now=now, research_version=research_version,
                                   retain_stale_observations=True)
    return {**deepcopy(legacy), **project_independent_price_conditions(root,
        items=legacy.get("items", []), now=now, allow_test_only=allow_test_only)}
