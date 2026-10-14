"""Read-time revalidation of a frozen value plan without new approvals."""
from datetime import datetime
from pathlib import Path

from .value_action_plan import load_registered_value_action_plans


def revalidate_current_value_plan(root: Path, frozen: dict, *, now: datetime) -> dict:
    if frozen.get("schema_version") != "value-action-plan-v1":
        return frozen
    current = load_registered_value_action_plans(root, now=now, symbols=[frozen["symbol"]])
    rebuilt = next((row for row in current["items"] if row["symbol"] == frozen["symbol"]), None)
    fields = ("research_version", "valuation_input_version", "bear", "base", "bull",
              "reference_close", "market_trade_date", "safety_margin_policy",
              "price_comparison_eligible", "entry_condition", "add_condition", "reduce_condition", "exit_condition")
    if rebuilt is not None and all(rebuilt.get(key) == frozen.get(key) for key in fields):
        return frozen
    # Retain the immutable prior packet itself for historical review, while the
    # current view must not reuse conditions whose source/date no longer checks.
    result = {**frozen, "signal_state": "STALE" if rebuilt else "BLOCKED", "action_intent": "WATCH",
              "action_eligibility": False, "formal_eligibility": False, "portfolio_eligibility": None,
              "price_comparison_eligible": False, "current_reference_price": None, "reference_close": None,
              "bear": None, "base": None, "bull": None, "conditional_valuation_range": None,
              "invalidation_price": None,
              "blockers": list(dict.fromkeys([*frozen.get("blockers", []), "CURRENT_VALUE_PLAN_CHANGED_OR_STALE", *current["blockers"]])),
              "explanation": "本次读取无法重现已发布估值与价格条件；旧方案仅保留在历史版本，当前不作为操作依据。"}
    for action in ("entry", "add", "reduce", "exit"):
        result[action + "_condition"] = None
        result[action + "_trigger_price"] = None
    return result
