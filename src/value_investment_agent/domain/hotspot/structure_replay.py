"""Prefix-only descriptions using Root's registered rule unchanged."""
from bisect import bisect_right
from collections import Counter
from decimal import Decimal

from .confirmed_price_structure import RULE_VERSION, analyze_price_behavior
from .current_price import current_signal
from .event_replay import validate_spec
from .price_action_plan import calculate_price_levels


def completed_prefix(bars: dict, cutoff: str) -> dict:
    result = {}
    for period in ("daily", "60m", "15m"):
        keys = [row["time"] + " 15:00:00" if period == "daily" else row["time"] for row in bars[period]]
        result[period] = bars[period][:bisect_right(keys, cutoff)]
    return result


def describe_prefix(prefix: dict) -> dict:
    counts = {period: len(prefix[period]) for period in ("daily", "60m", "15m")}
    missing = [period for period, count in counts.items() if count < 6]
    if missing:
        return {"status": "MISSING_COMPLETED_BAR_WINDOW", "bar_counts": counts,
                "missing_periods": missing, "rule_version": RULE_VERSION,
                "structure": None, "formal_eligibility": False, "action": "no_order"}
    structure = analyze_price_behavior(prefix)
    return {"status": "DESCRIPTIVE_OBSERVATION_NOT_ADMITTED", "bar_counts": counts,
            "missing_periods": [], "rule_version": RULE_VERSION, "structure": structure,
            "confirmed_trend_history": "INSUFFICIENT_CONFIRMED_SWINGS" if structure["daily_trend"] == "UNKNOWN" else "AVAILABLE",
            "formal_eligibility": False, "action": "no_order"}


def observe_structure_prefixes(bars: dict, spec: dict) -> dict:
    validate_spec(spec)
    for period in ("daily", "60m", "15m"):
        calculate_price_levels(bars[period], period=period)
    summaries = {key: {
        "cutoffs": 0, "complete_raw_windows": 0, "missing_raw_windows": 0,
        "insufficient_confirmed_trend": 0, "v1_trigger_count": 0,
        "next_bar_confirmation_count": 0, "pullback_recovery_count": 0,
        "risk_reward_available_count": 0, "price_condition_mismatch_count": 0,
        "v1_state_transitions": 0, "daily_trend_transitions": 0,
        "compared_consecutive_pairs": 0, "daily_trend_counts": Counter(),
        "observation_quality_counts": Counter(),
    } for key in ("development", "validation")}
    prior = {key: None for key in summaries}
    records, last = [], None
    for index, row in enumerate(bars["60m"]):
        cutoff = row["time"]
        day = cutoff[:10]
        if index < 5 or not spec["start_date"] <= day <= spec["end_date"]:
            continue
        segment = "development" if day <= spec["development_end"] else "validation"
        summary = summaries[segment]
        summary["cutoffs"] += 1
        prefix = completed_prefix(bars, cutoff)
        described = describe_prefix(prefix)
        v1 = calculate_price_levels(prefix["60m"][-6:], period="60m")
        state, _ = current_signal({"60m": v1})
        summary["v1_trigger_count"] += state == "TRIGGER_OBSERVED"
        record = {"cutoff": cutoff, "segment": segment, "window_status": described["status"],
                  "bar_counts": described["bar_counts"], "v1_signal_state": state,
                  "v1_entry_trigger_price": v1["entry_trigger_price"],
                  "v1_invalidation_price": v1["invalidation_price"]}
        structure = described["structure"]
        if structure is None:
            summary["missing_raw_windows"] += 1
            record["missing_periods"] = described["missing_periods"]
            prior[segment] = None
        else:
            summary["complete_raw_windows"] += 1
            summary["insufficient_confirmed_trend"] += structure["daily_trend"] == "UNKNOWN"
            summary["daily_trend_counts"][structure["daily_trend"]] += 1
            summary["observation_quality_counts"][structure["observation_quality"]] += 1
            summary["next_bar_confirmation_count"] += structure["breakout"]["confirmed_on_next_completed_bar"]
            summary["pullback_recovery_count"] += structure["pullback_recovery"]["observed"]
            summary["risk_reward_available_count"] += structure["risk_reward_ratio"] is not None
            matched = (Decimal(structure["breakout"]["level"]) == Decimal(v1["entry_trigger_price"])
                       and Decimal(structure["structural_protection_price"]) == Decimal(v1["invalidation_price"])
                       and structure["breakout"]["observed"] == v1["breakout_observed"])
            summary["price_condition_mismatch_count"] += not matched
            record.update(daily_trend=structure["daily_trend"],
                          confirmed_trend_history=described["confirmed_trend_history"],
                          next_bar_confirmation=structure["breakout"]["confirmed_on_next_completed_bar"],
                          pullback_recovery=structure["pullback_recovery"]["observed"],
                          structural_risk_reward_ratio=structure["risk_reward_ratio"],
                          observation_quality=structure["observation_quality"],
                          inherited_price_conditions_match=matched,
                          latest_daily_bar=prefix["daily"][-1]["time"],
                          latest_auxiliary_bar=prefix["15m"][-1]["time"])
            for point in structure["confirmed_swings"]:
                if point["known_at"] + " 15:00:00" > cutoff:
                    raise ValueError("Unconfirmed future daily swing leaked into prefix")
            if prior[segment] is not None:
                summary["compared_consecutive_pairs"] += 1
                summary["v1_state_transitions"] += state != prior[segment][0]
                summary["daily_trend_transitions"] += structure["daily_trend"] != prior[segment][1]
            prior[segment] = (state, structure["daily_trend"])
        records.append(record)
        last = {"cutoff": cutoff, **described}
    for summary in summaries.values():
        for key in ("daily_trend_counts", "observation_quality_counts"):
            summary[key] = dict(sorted(summary[key].items()))
        count = summary["compared_consecutive_pairs"]
        for key in ("v1_state_transitions", "daily_trend_transitions"):
            summary[key + "_fraction"] = str(Decimal(summary[key]) / count) if count else None
    return {"rule_version": RULE_VERSION, "prefix_records": records, "segments": summaries,
            "last_observation": last, "parameters_changed": False,
            "stability_scope": "STATE_TRANSITIONS_ONLY_NOT_SIGNAL_EDGE_OR_PROFITABILITY",
            "prospective_oos_admitted": False, "strict_pit_admitted": False,
            "formal_eligibility": False, "portfolio_eligibility": None, "action": "no_order"}
