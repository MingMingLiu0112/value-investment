"""Public outcome assembly over existing plans; never an admission verifier."""
from __future__ import annotations

from copy import deepcopy
import re
from datetime import datetime

from .value_action_plan import CoreValuePublicReviews

from ...domain.hotspot.independent_admission import GATES, RULE_VERSION


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


def _hotspot_evaluation_complete(plan):
    admission = plan.get("independent_admission")
    if (plan.get("schema_version") != "price-action-plan-independent-v2"
            or plan.get("current_data_status") != "CURRENT"
            or not isinstance(admission, dict)
            or admission.get("schema_version") != RULE_VERSION
            or admission.get("symbol") != plan["symbol"]
            or admission.get("rule_version") != plan.get("model_or_rule_version")
            or admission.get("action") != "no_order"
            or admission.get("review_status") != "VERIFIED"):
        return False
    # An evidenced FAIL is an evaluated veto, unlike missing/unknown/expired
    # evidence. Neither a PASS label nor personal trade eligibility is required.
    evaluated_vetoes = {gate + ":FAIL" for gate in GATES}
    for blockers, allowed in ((admission.get("blockers"), evaluated_vetoes),
            (plan.get("blockers"), evaluated_vetoes | {
                "CURRENT_STRUCTURE_NOT_QUALIFIED", "CURRENT_ENTRY_CONDITION_NOT_OBSERVED",
                "CURRENT_ADD_CONDITION_NOT_CONFIRMED"})):
        if (not isinstance(blockers, list) or any(not isinstance(x, str) for x in blockers)
                or not set(blockers) <= allowed):
            return False
    return True


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


def project_actionable_evaluation(item: dict, *,
        core_reviews: CoreValuePublicReviews | None = None, now: datetime | None = None) -> dict:
    """Explain a public plan's outcome, without promoting it to personal authority.

    A public quote/plan never proves account capacity or ownership. Personal
    actions remain owned by the registered-plan/private-risk application path.
    """
    plan = item.get("price_action_plan")
    result = {
        "symbol": item.get("symbol"), "company_name": item.get("name"),
        "strategy": "HOTSPOT_SATELLITE" if item.get("strategy") in {
            "hotspot", "HOTSPOT_SATELLITE"} else "CORE_VALUE",
        "decision_action": "UNASSESSABLE", "action": "no_order",
        "decision_layer": "STRATEGY_VERDICT",
        "personal_action_review": {"state": "UNASSESSABLE", "reason": "PRIVATE_RISK_NOT_EVALUATED"},
        "evaluation_status": "NOT_ASSESSABLE",
        "decision_reason": "财务、研究或价格计划证据不足，不能形成可操作判断。",
        "personal_risk_status": "NOT_EVALUATED_PUBLIC_VIEW",
        "eligibility": False, "position_range": None, "review_quantity": None,
        "available_cash_impact": None, "expected_fees_and_slippage": None,
        "formal_review_status": "UNKNOWN", "evidence_refs": [],
    }
    if not isinstance(plan, dict):
        return result
    try:
        view = project_strategy_decision(plan, symbol=item.get("symbol"))
        add_condition = _condition(plan["add_condition"]) if isinstance(plan.get("add_condition"), dict) else None
        reduce_condition = _condition(plan["reduce_condition"]) if isinstance(plan.get("reduce_condition"), dict) else None
    except (ValueError, TypeError):
        return result
    result.update({
        "strategy": view["strategy"], "data_trade_date": plan.get("market_trade_date"),
        "research_or_structure_version": view["rule_version"],
        "formal_review_status": view["review_status"],
        "evidence_refs": view["evidence_refs"],
        "current_verified_reference_price": (plan.get("reference_close") if plan.get("current_quote_verified") is True else None)
            if view["strategy"] == "CORE_VALUE" else plan.get("current_reference_price"),
        "entry_condition": view["entry_condition"],
        "entry_price_or_range": plan.get("entry_trigger_price"),
        "add_condition": add_condition,
        "reduce_condition": reduce_condition,
        "exit_condition": view["exit_condition"],
        "invalidation_condition": view["invalidation_condition"],
        "plan_expiry": plan.get("expires_after_session") or plan.get("valid_until"),
        "required_confirmation": list(plan.get("blockers") or []),
    })
    state = plan.get("signal_state")
    if view["strategy"] == "CORE_VALUE":
        intent = (core_reviews.action_for(plan, now=now)
                  if isinstance(core_reviews, CoreValuePublicReviews) and now is not None else None)
        if intent in {'OPEN', 'ADD', 'HOLD', 'REDUCE', 'EXIT'}:
            labels = {'OPEN': '建仓', 'ADD': '加仓', 'HOLD': '持有', 'REDUCE': '减仓', 'EXIT': '退出'}
            result.update(decision_action='CONDITIONAL_MANUAL_REVIEW',
                evaluation_status='EVALUATED_CONDITIONAL_REVIEW', public_action_intent=intent,
                decision_reason=f'原生证券研究与本次条件计划已重新核验，可进行{labels[intent]}条件的人工复核；'
                    '这不是个人操作许可，不推断实际持仓；资金、数量和个人风险仍需独立核验。',
                hold_condition=_condition(plan.get('hold_condition')))
            return result
        formal_gaps = plan.get("formal_eligibility_blockers") or []
        if "VALUE_PREDECISION_G3_EVENT_MODEL_PRICE_GATE_NOT_PASSED" in formal_gaps:
            result["decision_reason"] = "研究经济假设、重大事件或估值审核未通过，不能形成可信建加仓结论。"
            return result
        if plan.get("qualification") == "RESEARCH_SCENARIO":
            result["decision_reason"] = "估值或适用价格政策证据不足；研究情景不是已批准的建仓价格。"
            return result
    if state == "BLOCKED":
        if view["strategy"] == "CORE_VALUE":
            result["decision_reason"] = "研究估值或操作政策尚未形成可用依据；已取得行情也不能代替研究。"
        elif "CURRENT_CASE_CHANGED_OR_STALE" in result["required_confirmation"] or not plan.get("price_behavior"):
            result["decision_reason"] = "当前价格结构或原始证据未通过核验，暂不能形成波段操作判断。"
        else:
            result["decision_reason"] = "波段结构已有观察，但独立策略验证、事件或风险前置未通过；不是价值估值未通过。"
        result["current_verified_reference_price"] = None
        return result
    if state in {"STALE", "EXPIRED", "HISTORICAL_OBSERVATION_NOT_ADMITTED"}:
        result["decision_reason"] = "行情或计划失效，不能据此判断当前是否存在交易机会。"
        result["current_verified_reference_price"] = None
        return result
    behavior = plan.get("price_behavior") or {}
    if not isinstance(behavior, dict):
        return result
    if not view["evidence_refs"]:
        result["decision_reason"] = "计划未提供可追溯证据引用，不能把状态标签当作已完成评价。"
        return result
    if view["strategy"] == "HOTSPOT_SATELLITE" and not _hotspot_evaluation_complete(plan):
        result["decision_reason"] = (
            "已有价格结构观察，但独立策略、事件、执行或时点依据尚不完整；"
            "即使入场未触发，也不能将证据不足表述为已充分评价的不交易结论。")
        return result
    entry = plan.get("entry_condition") or {}
    entry_known = isinstance(entry, dict) and entry.get("price") is not None
    if view["strategy"] == "HOTSPOT_SATELLITE":
        periods = plan.get("period_structure") or {}
        entry_known = (entry_known and isinstance(periods, dict)
            and all(periods.get(period) not in {None, "UNKNOWN", "INSUFFICIENT_DATA"} for period in ("60m", "15m"))
            and behavior.get("daily_trend") in {"UPTREND", "RANGE"})
    else:
        entry_known = entry_known and plan.get("price_comparison_eligible") is True
    if state in {"INVALIDATED", "TRIGGER_REJECTED"}:
        result.update(evaluation_status="EVALUATED_NO_TRADE",
                      decision_reason="已评价的价格结构失效或触发被拒绝，不新建仓；已有持仓须另行核验退出条件。")
    elif behavior.get("daily_trend") == "DOWNTREND" or behavior.get("observation_quality") == "INSUFFICIENT_UPPER_SPACE":
        result.update(evaluation_status="EVALUATED_NO_TRADE",
                      decision_reason="已评价的趋势或上方交易空间不满足入场规则，不新建仓。")
    elif state in {"TRIGGER_PENDING", "WATCH"} and entry_known and (
            entry.get("triggered") is False or entry.get("observed") is False):
        result.update(evaluation_status="EVALUATED_NO_TRADE",
                      decision_reason="已形成条件计划，但价格或完整周期确认条件尚未满足，不新建仓。")
    elif state in {"ACTION_ELIGIBLE", "TRIGGER_OBSERVED", "OBSERVED", "VALIDATION_PENDING"}:
        result["decision_reason"] = "证券级条件已有结果，但正式准入或个人资金风险未核验，当前不形成个人交易动作。"
    if result["evaluation_status"] == "EVALUATED_NO_TRADE":
        result["decision_action"] = "NO_TRADE"
    return result


def summarize_actionable_evaluations(items: list[dict], *,
        core_reviews: CoreValuePublicReviews | None = None, now: datetime | None = None) -> dict:
    rows = []
    for item in items:
        try:
            rows.append(project_actionable_evaluation(item, core_reviews=core_reviews, now=now))
        except (ValueError, TypeError, KeyError, ArithmeticError):
            # A failed display contract cannot erase independent companies.
            rows.append(project_actionable_evaluation({key: item.get(key)
                for key in ("symbol", "name", "strategy")}))
    conditional = sum(row['evaluation_status'] == 'EVALUATED_CONDITIONAL_REVIEW' for row in rows)
    assessed = sum(row["evaluation_status"] in {'EVALUATED_NO_TRADE', 'EVALUATED_CONDITIONAL_REVIEW'} for row in rows)
    return {"action": "no_order", "items": rows, "scope": "PUBLISHED_COMPANIES_ONLY",
            "evaluated_count": assessed, "unassessable_count": len(rows) - assessed,
            "operation_eligible_count": 0,
            "conditional_review_count": conditional,
            "conclusion": "INCOMPLETE_EVALUATION" if assessed != len(rows) or not rows
                          else 'PUBLIC_CONDITIONAL_REVIEWS_AVAILABLE' if conditional else "NO_QUALIFIED_NEW_TRADE"}
