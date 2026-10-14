"""Research-only tactical price plan from a verified historical case."""

from copy import deepcopy


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
