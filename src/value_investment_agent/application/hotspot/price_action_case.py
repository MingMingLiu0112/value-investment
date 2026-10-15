"""Research-only tactical price plan from a verified historical case."""

from copy import deepcopy
from decimal import Decimal
from datetime import datetime

from value_investment_agent.domain.hotspot.current_price import CURRENT_BLOCKERS, current_signal
from value_investment_agent.domain.hotspot.confirmed_price_structure import analyze_price_behavior, conditional_action_rules


def project_price_action_plan(case: dict) -> dict:
    if (case.get("action") != "no_order" or
            case.get("signal_state") != "HISTORICAL_OBSERVATION_NOT_ADMITTED"):
        raise ValueError("Historical price case is not research-only")
    level = case["levels"]["60m"]
    if level.get("action") != "no_order":
        raise ValueError("Level cannot authorize an order")
    return {
        "schema_version": "price-action-plan-historical-v1",
        "symbol": case["symbol"],
        "strategy": "HOTSPOT_SATELLITE",
        "market_trade_date": case["market_trade_date"],
        "data_available_at": max(binding["fetched_at"]
                                 for binding in case["source_bindings"].values()),
        "source_bindings": deepcopy(case["source_bindings"]),
        "current_reference_price": case["current_reference_price"],
        "reference_price_scope": "HISTORICAL_CLOSE_NOT_CURRENT_QUOTE",
        "trend_state": "NOT_ASSESSED",
        "entry_trigger_price": level["entry_trigger_price"],
        "entry_confirmation_rule": level["entry_confirmation_rule"],
        "add_trigger_price": None,
        "reduce_trigger_price": None,
        "exit_trigger_price": None,
        "invalidation_price": level["invalidation_price"],
        "invalidation_rule": level["invalidation_rule"],
        "risk_reward_ratio": None,
        "signal_state": "HISTORICAL_OBSERVATION_NOT_ADMITTED",
        "action_eligibility": False,
        "evidence_refs": list(dict.fromkeys(
            binding["sha256"] for binding in case["source_bindings"].values())),
        "blockers": list(case["blockers"]),
        "model_or_rule_version": level["rule_version"],
        "action": "no_order",
    }


def project_current_price_action_plan(case: dict) -> dict:
    """Project a loader-verified current case with the historical plan fields."""
    display = case.get("observation_scope") == "LAST_COMPLETED_CLOSE_DISPLAY_ONLY"
    expected_close = "VERIFIED_LAST_COMPLETED_CLOSE_DISPLAY_ONLY" if display else "VERIFIED_DUAL_SOURCE_CLOSE"
    if (case.get("schema_version") != "hotspot-current-price-case-v1"
            or case.get("action") != "no_order" or case.get("action_eligibility") is not False
            or case.get("blockers") != CURRENT_BLOCKERS
            or case.get("current_reference_close", {}).get("status") != expected_close
            or (display and any(case.get(key) is not False for key in
                                ("current_pit", "formal_eligibility", "price_admitted")))):
        raise ValueError("Current case is not verified research-only evidence")
    state, explanation = current_signal(case["levels"])
    if case.get("signal_state") != state or case.get("explanation") != explanation:
        raise ValueError("Current signal contract mismatch")
    historical_view = {**case, "signal_state": "HISTORICAL_OBSERVATION_NOT_ADMITTED"}
    plan = project_price_action_plan(historical_view)
    plan.update(schema_version="price-action-plan-current-v1", signal_state=state,
                explanation=explanation, primary_timeframe="60m",
                reference_price_scope="LATEST_COMPLETED_SESSION_DUAL_SOURCE_CLOSE",
                current_reference_close=deepcopy(case["current_reference_close"]),
                levels={period: dict(prior_max_high=item["entry_trigger_price"],
                                     prior_min_low=item["invalidation_price"],
                                     volume_ratio=item["volume_ratio"], last_close=item["reference_close"])
                        for period, item in case["levels"].items()},
                next_completed_eligible_session=case["current_reference_close"]["next_session"],
                next_session_date=case["current_reference_close"]["next_session"],
                support=["完整已收盘分钟线；日线由分钟线聚合；收盘已通过腾讯与新浪双源核对。"],
                counter=["分钟价格结构仍为单一来源，不能视为独立双源技术信号。",
                         "多周期趋势、重大事件、PIT/OOS、成本与 Shadow 门禁未完成。"],
                next_session_rule="Only after the next session completes and all independent gates pass",
                trend_state="NOT_ASSESSED", action_eligibility=False)
    plan["evidence_refs"] = list(dict.fromkeys([
        *plan["evidence_refs"], case["current_reference_close"]["bundle_sha256"],
        *case["current_reference_close"]["evidence_refs"]]))
    structures = {period: ("BREAKOUT" if item["breakout_observed"] else
                  "INVALIDATED" if Decimal(item["reference_close"]) < Decimal(item["invalidation_price"]) else
                  "PRICE_ABOVE_VOLUME_PENDING" if Decimal(item["reference_close"]) > Decimal(item["entry_trigger_price"]) else "RANGE")
                  for period, item in case["levels"].items()}
    plan.update(period_structure=structures,
                trend_state="MULTIPERIOD_BREAKOUT_OBSERVED" if all(s == "BREAKOUT" for s in structures.values()) else "NOT_CONFIRMED",
                action_intent="OPEN" if state == "TRIGGER_OBSERVED" else "EXIT" if state == "TRIGGER_REJECTED" else "WATCH",
                formal_eligibility=False, portfolio_eligibility=None, sleeve="HOTSPOT_SATELLITE",
                entry_condition=dict(price=plan["entry_trigger_price"], rule=plan["entry_confirmation_rule"], status=state),
                add_condition=None, reduce_condition=None,
                exit_condition=dict(price=plan["invalidation_price"], rule=plan["invalidation_rule"]),
                invalidation_condition=dict(price=plan["invalidation_price"], rule=plan["invalidation_rule"]),
                security_risk_trigger=dict(kind="STRUCTURE_INVALIDATION", observed=state == "TRIGGER_REJECTED",
                                           rule_version=plan["model_or_rule_version"],
                                           review_intent="EXIT", personal_sell_permission=False),
                valid_from_session=case["market_trade_date"],
                expires_after_session=case["current_reference_close"]["next_session"],
                expiry_rule="Refresh after next completed exchange session; old conditions must not remain current",
                next_observation="下一完整60分钟收盘重新检查价格与量能；次一交易日收盘后重新筛选。")
    plan["price_behavior"] = analyze_price_behavior(case["bars"])
    rules = conditional_action_rules(plan["price_behavior"], case["levels"]["60m"])
    plan.update(conditional_action_rules=rules,
                entry_condition={**plan["entry_condition"], **rules["OPEN"], "status": state},
                add_condition=rules["ADD"], reduce_condition=rules["REDUCE"],
                exit_condition=rules["EXIT"])
    plan["risk_reward_ratio"] = plan["price_behavior"]["risk_reward_ratio"]
    plan["data_available_at"] = max(datetime.fromisoformat(value) for value in [
        *(source["fetched_at"] for source in case["source_bindings"].values()),
        case["verified_available_at"]]).isoformat()
    if display:
        plan.update(reference_price_scope="LAST_COMPLETED_CLOSE_DISPLAY_ONLY",
            observation_scope="LAST_COMPLETED_CLOSE_DISPLAY_ONLY", current_pit=False,
            formal_eligibility=False, price_admitted=False, action_eligibility=False,
            next_completed_eligible_session=None, next_session_date=None,
            support=["双源最近已完成交易日收盘与完整分钟线观察；原件取得时间晚于报价时点，不证明历史PIT或正式准入。"],
            next_session_rule="Display-only completed-close observation; refresh after each completed session")
    return plan
