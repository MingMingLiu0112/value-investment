"""Read-time revalidation of a frozen value plan without new approvals."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .value_action_plan import load_registered_value_action_plans


def revalidate_current_value_plan(root: Path, frozen: dict, *, now: datetime) -> dict:
    if frozen.get("schema_version") != "value-action-plan-v1":
        return frozen
    current = load_registered_value_action_plans(root, now=now, symbols=[frozen["symbol"]])
    rebuilt = next((row for row in current["items"] if row["symbol"] == frozen["symbol"]), None)
    if rebuilt is not None and all(frozen.get(key) == value for key, value in rebuilt.items()):
        return frozen
    # Retain the immutable prior packet itself for historical review, while the
    # current view must not reuse conditions whose source/date no longer checks.
    result = {**frozen, "signal_state": "STALE" if rebuilt else "BLOCKED", "action_intent": None,
              "action_eligibility": False, "formal_eligibility": False, "portfolio_eligibility": None,
              "price_comparison_eligible": False, "current_reference_price": None, "reference_close": None,
              "current_quote_verified": False,
              "current_quote_blockers": ["CURRENT_VERIFIED_QUOTE_NOT_AVAILABLE_IN_REBUILT_PLAN"],
              "bear": None, "base": None, "bull": None, "conditional_valuation_range": None,
              "invalidation_price": None,
              "blockers": list(dict.fromkeys([*frozen.get("blockers", []), "CURRENT_VALUE_PLAN_CHANGED_OR_STALE", *current["blockers"]])),
              "explanation": "本次读取无法重现已发布估值与价格条件；旧方案仅保留在历史版本，当前不作为操作依据。"}
    # A new verified quote remains an observable fact even when old economics
    # cannot be reproduced. Never reuse the frozen quote's verification flag.
    if rebuilt is not None and rebuilt.get("current_quote_verified") is True:
        try:
            price = Decimal(str(rebuilt.get("reference_close")))
            if (not price.is_finite() or price <= 0 or not rebuilt.get("market_trade_date")
                    or not rebuilt.get("source_bindings")):
                raise ValueError('Rebuilt verified quote is incomplete')
        except (InvalidOperation, ValueError):
            pass
        else:
            result.update(reference_close=str(price), current_reference_price=str(price),
                market_trade_date=rebuilt["market_trade_date"], current_quote_verified=True,
                current_quote_blockers=[], reference_price_scope="CURRENT_VERIFIED_CLOSE_NOT_VALUATION_COMPARABLE",
                source_bindings=rebuilt["source_bindings"])
    for action in ("entry", "add", "reduce", "exit"):
        result[action + "_condition"] = None
        result[action + "_trigger_price"] = None
    return result
