"""Frozen v1 completed-bar observations, never a historical execution engine."""
from bisect import bisect_right
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

from .current_price import current_signal
from .price_action_plan import RULE_VERSION, calculate_price_levels


def validate_spec(spec: dict) -> None:
    if (spec.get("schema_version") != "hotspot-event-replay-spec-v1"
            or spec.get("action") != "no_order" or spec.get("rule_version") != RULE_VERSION
            or spec.get("primary_period") != "60m"
            or type(spec.get("forward_sessions")) is not int or spec["forward_sessions"] != 5):
        raise ValueError("Unsupported frozen replay specification")
    start, development, validation, end = (
        date.fromisoformat(spec[key]) for key in
        ("start_date", "development_end", "validation_start", "end_date"))
    if not start <= development < validation <= end or validation != development + timedelta(days=1):
        raise ValueError("Invalid chronological partition")


def _average(values: list[str]) -> str | None:
    return str(sum(map(Decimal, values)) / len(values)) if values else None


def _outcome(rows: list[dict], index: int, levels: dict, *, boundary: str) -> dict:
    """Frozen references, forward observations only, and explicit right censoring."""
    stamp = rows[index]["time"]
    future = [row for row in rows[index + 1:] if row["time"][:10] <= boundary]
    days = sorted({row["time"][:10] for row in future if row["time"][:10] > stamp[:10]})[:5]
    fifth_day = days[4] if len(days) == 5 else None
    end = fifth_day or (days[-1] if days else stamp[:10])
    followed = [row for row in future if row["time"][:10] <= end]
    reference = Decimal(levels["reference_close"])
    trigger = Decimal(levels["entry_trigger_price"])
    invalidation = Decimal(levels["invalidation_price"])
    breach = next((row["time"] for row in followed if Decimal(row["close"]) < invalidation), None)
    next_close = next((row for row in followed if days and row["time"] == days[0] + " 15:00:00"), None)
    fifth_close = next((row for row in followed if fifth_day and row["time"] == fifth_day + " 15:00:00"), None)
    complete = fifth_close is not None
    next_complete = next_close is not None
    false_rows = [row for row in followed if days and row["time"] <= days[0] + " 15:00:00"]
    return {
        "scope": "SIGNAL_CLOSE_PRICE_PATH_NOT_TRADE_RETURN",
        "horizon_complete": complete,
        "observed_followup_sessions": len(days),
        "last_observed_bar": followed[-1]["time"] if followed else None,
        "right_censored": not complete,
        "first_invalidation_observed_at": breach,
        "failed_within_five_sessions": breach is not None if complete else None,
        "false_breakout_next_session_proxy": (
            any(Decimal(row["close"]) <= trigger for row in false_rows) if next_complete else None),
        "next_session_close_change_pct": (
            str((Decimal(next_close["close"]) / reference - 1) * 100) if next_complete else None),
        "fifth_session_close_change_pct": (
            str((Decimal(fifth_close["close"]) / reference - 1) * 100) if complete else None),
        "adverse_excursion_from_signal_close_pct": (
            str(min(Decimal(0), (min(Decimal(row["low"]) for row in followed) / reference - 1) * 100))
            if complete else None),
        "execution": {
            "status": "UNKNOWN_NOT_SIMULATED", "fill": None, "unfilled": None,
            "cost_cny": None, "slippage_cny": None, "net_trade_return_pct": None,
            "trade_mae_pct": None, "t_plus_one_exit_feasibility": "UNKNOWN",
            "protection_price_guarantees_fill": False,
        },
    }


def _summary(events: list[dict], states: Counter) -> dict:
    complete = [row for row in events if row["outcome"]["horizon_complete"]]
    false_known = [row for row in events if row["outcome"]["false_breakout_next_session_proxy"] is not None]
    changes = [row["outcome"]["fifth_session_close_change_pct"] for row in complete]
    excursions = [row["outcome"]["adverse_excursion_from_signal_close_pct"] for row in complete]
    false_count = sum(row["outcome"]["false_breakout_next_session_proxy"] for row in false_known)
    failed_count = sum(row["outcome"]["failed_within_five_sessions"] for row in complete)
    return {
        "completed_cutoff_count": sum(states.values()), "state_counts": dict(sorted(states.items())),
        "trigger_count": len(events), "mature_five_session_count": len(complete),
        "right_censored_count": len(events) - len(complete),
        "failure_proxy_count": failed_count,
        "failure_proxy_denominator": len(complete),
        "failure_proxy_rate": str(Decimal(failed_count) / len(complete)) if complete else None,
        "false_breakout_proxy_count": false_count,
        "false_breakout_proxy_denominator": len(false_known),
        "false_breakout_proxy_rate": str(Decimal(false_count) / len(false_known)) if false_known else None,
        "mean_fifth_close_change_pct": _average(changes),
        "mean_positive_price_change_pct": _average([x for x in changes if Decimal(x) > 0]),
        "mean_negative_price_change_pct": _average([x for x in changes if Decimal(x) < 0]),
        "worst_signal_close_adverse_excursion_pct": str(min(map(Decimal, excursions))) if excursions else None,
        "net_return_distribution": None, "average_trade_win": None, "average_trade_loss": None,
        "verified_fill_count": None, "verified_unfilled_count": None,
        "independent_trade_sample_count": None,
        "overlapping_events_are_not_independent": True,
        "market_environment": "NOT_ASSESSED_BY_FROZEN_V1",
        "pullback_rule_performance": None,
    }


def replay_v1(bars_by_period: dict, spec: dict) -> dict:
    """Evaluate only available-at-cutoff bars, label later paths separately."""
    validate_spec(spec)
    times = {}
    for period in ("daily", "60m", "15m"):
        calculate_price_levels(bars_by_period[period], period=period)
        times[period] = [bar["time"] for bar in bars_by_period[period]]
    rows = bars_by_period["60m"]
    events = {"development": [], "validation": []}
    states = {key: Counter() for key in events}
    last = None
    for index in range(5, len(rows)):
        stamp = rows[index]["time"]
        day = stamp[:10]
        if not spec["start_date"] <= day <= spec["end_date"]:
            continue
        segment = "development" if day <= spec["development_end"] else "validation"
        levels = calculate_price_levels(rows[index - 5:index + 1], period="60m")
        state, _ = current_signal({"60m": levels})
        states[segment][state] += 1
        last = {"cutoff": stamp, "signal_state": state, "levels": levels}
        if state != "TRIGGER_OBSERVED":
            continue
        context = {}
        for period in ("daily", "15m"):
            # A daily candle is known only at its close, never at 10:30/11:30/14:00.
            keys = ([value + " 15:00:00" for value in times[period]] if period == "daily" else times[period])
            count = bisect_right(keys, stamp)
            context[period] = (
                calculate_price_levels(bars_by_period[period][count - 6:count], period=period)
                if count >= 6 else None)
        boundary = spec["development_end"] if segment == "development" else spec["end_date"]
        events[segment].append({
            "cutoff": stamp, "signal_state": state, "rule_version": RULE_VERSION,
            "levels": levels, "completed_context": context,
            "outcome": _outcome(rows, index, levels, boundary=boundary),
            "formal_eligibility": False, "portfolio_eligibility": None, "action": "no_order",
        })
    return {
        "rule_version": RULE_VERSION, "events": events, "last_observation": last,
        "segments": {key: _summary(events[key], states[key]) for key in events},
        "historical_classification_used": False,
        "strict_pit_admitted": False, "strict_oos_admitted": False,
        "performance_claim_allowed": False, "action": "no_order",
    }
