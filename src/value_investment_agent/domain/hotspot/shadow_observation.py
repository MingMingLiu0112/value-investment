"""Real completed observation baselines; no scheduling or paper executions."""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from .price_action_plan import RULE_VERSION


def make_shadow_baseline(case: dict, plan: dict, *, observed_at: datetime) -> dict:
    if observed_at.utcoffset() is None:
        raise ValueError("Timezone-aware observation required")
    if (case.get("action") != "no_order" or plan.get("action") != "no_order"
            or plan.get("action_eligibility") is not False
            or plan.get("model_or_rule_version") != RULE_VERSION
            or plan.get("symbol") != case.get("symbol")
            or plan.get("market_trade_date") != case.get("market_trade_date")
            or plan.get("signal_state") != case.get("signal_state")):
        raise ValueError("Shadow case/plan contract mismatch")
    latest = case["bars"]["60m"][-1]["time"]
    cutoff = datetime.fromisoformat(latest).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    if cutoff > observed_at:
        raise ValueError("Future bars cannot create Shadow observations")
    available = datetime.fromisoformat(case["data_available_at"])
    if available.utcoffset() is None or available > observed_at:
        raise ValueError("Shadow inputs not yet available")
    return {
        "schema_version": "hotspot-read-only-shadow-baseline-v1",
        "symbol": case["symbol"], "market_trade_date": case["market_trade_date"],
        "observed_at": observed_at.isoformat(), "cutoff": latest,
        "data_available_at": available.isoformat(),
        "rule_version": RULE_VERSION, "case_sha256": case["case_sha256"],
        "signal_state": plan["signal_state"],
        "current_reference_price": plan["current_reference_price"],
        "entry_trigger_price": plan["entry_trigger_price"],
        "invalidation_price": plan["invalidation_price"],
        "previous_judgment": None, "today_vs_previous_outcome": None,
        "trigger_observed": plan["signal_state"] == "TRIGGER_OBSERVED",
        "invalidation_observed": plan["signal_state"] == "TRIGGER_REJECTED",
        "execution_feasibility": "UNKNOWN", "potential_cost": None,
        "outside_rule_changes": "NOT_REVIEWED",
        "elapsed_real_shadow_sessions": 0, "real_trade": False,
        "formal_eligibility": False, "portfolio_eligibility": None, "action": "no_order",
    }


def compare_archived_baseline(prior: dict, current: dict) -> dict:
    """Compare a genuine earlier baseline, not a retrospectively invented plan."""
    if (prior.get("schema_version") != "hotspot-read-only-shadow-baseline-v1"
            or current.get("schema_version") != prior["schema_version"]
            or prior.get("action") != "no_order" or current.get("action") != "no_order"
            or prior.get("symbol") != current.get("symbol")
            or prior.get("rule_version") != current.get("rule_version")
            or prior["market_trade_date"] >= current["market_trade_date"]
            or datetime.fromisoformat(prior["observed_at"]) >= datetime.fromisoformat(current["observed_at"])
            or datetime.fromisoformat(prior["observed_at"]).date().isoformat() >= current["market_trade_date"]):
        raise ValueError("Prior contemporaneous archived baseline required")
    close = Decimal(current["current_reference_price"])
    return {
        "prior_case_sha256": prior["case_sha256"], "current_case_sha256": current["case_sha256"],
        "close_above_prior_trigger": close > Decimal(prior["entry_trigger_price"]),
        "close_below_prior_invalidation": close < Decimal(prior["invalidation_price"]),
        "volume_confirmation": "NOT_REASSESSED_FOR_PRIOR_FROZEN_WINDOW",
        "real_trade": False, "profit": None, "action": "no_order",
    }
