"""Research-only tactical price plan from a verified historical case."""

from copy import deepcopy

from value_investment_agent.domain.hotspot.current_price import CURRENT_BLOCKERS, current_signal


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
    if (case.get("schema_version") != "hotspot-current-price-case-v1"
            or case.get("action") != "no_order" or case.get("action_eligibility") is not False
            or case.get("blockers") != CURRENT_BLOCKERS
            or case.get("current_reference_close", {}).get("status") != "VERIFIED_DUAL_SOURCE_CLOSE"):
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
    return plan
