"""Descriptive prefix isolation; no prospective strategy-validation claim."""
from copy import deepcopy
from decimal import Decimal

from value_investment_agent.domain.hotspot.structure_replay import (
    completed_prefix, describe_prefix, observe_structure_prefixes,
)
from test_hotspot_event_replay import bars, spec, trigger


def test_sufficient_raw_window_is_distinct_from_missing_confirmed_trend():
    value = bars()
    output = describe_prefix(completed_prefix(value, "2026-07-01 15:00:00"))
    assert output["status"] == "DESCRIPTIVE_OBSERVATION_NOT_ADMITTED"
    assert all(count >= 6 for count in output["bar_counts"].values())
    assert output["confirmed_trend_history"] == "INSUFFICIENT_CONFIRMED_SWINGS"
    assert output["structure"]["daily_trend"] == "UNKNOWN"
    assert output["structure"]["risk_reward_ratio"] is None
    assert output["formal_eligibility"] is False


def test_incomplete_minute_window_is_explained_without_fake_structure():
    value = bars()
    value["15m"] = value["15m"][:4]
    output = describe_prefix(value)
    assert output["status"] == "MISSING_COMPLETED_BAR_WINDOW"
    assert output["missing_periods"] == ["15m"]
    assert output["structure"] is None


def test_daily_bar_and_swing_wait_for_completed_right_side_closes():
    value = bars()
    prices = [10, 11, 12, 11, 10, 11, 13, 12, 11]
    for row, price in zip(value["daily"], prices):
        row.update(open=str(price), close=str(price), high=str(price + 1), low=str(price - 1))
    pivot = value["daily"][6]["time"]
    known = value["daily"][8]["time"]
    early = describe_prefix(completed_prefix(value, known + " 14:00:00"))
    finished = describe_prefix(completed_prefix(value, known + " 15:00:00"))
    assert not any(point["pivot_at"] == pivot for point in early["structure"]["confirmed_swings"])
    assert any(point["pivot_at"] == pivot and point["known_at"] == known
               for point in finished["structure"]["confirmed_swings"])


def test_future_append_or_change_cannot_rewrite_previous_prefix_descriptions():
    value = bars()
    cutoff = "2026-07-01 10:30:00"
    trigger(value, cutoff)
    initial = observe_structure_prefixes(value, spec())
    modified = deepcopy(value)
    for period in modified:
        for row in modified[period]:
            known = row["time"] + " 15:00:00" if period == "daily" else row["time"]
            if known > cutoff:
                row.update(open="20", close="20", high="21", low="19", volume="1000")
    after = observe_structure_prefixes(modified, spec())
    assert [row for row in initial["prefix_records"] if row["cutoff"] <= cutoff] == [
        row for row in after["prefix_records"] if row["cutoff"] <= cutoff]


def test_new_descriptors_do_not_change_inherited_price_conditions_or_admission():
    value = bars()
    trigger(value, "2026-07-01 15:00:00")
    output = observe_structure_prefixes(value, spec())
    for summary in output["segments"].values():
        assert summary["price_condition_mismatch_count"] == 0
        assert summary["complete_raw_windows"] + summary["missing_raw_windows"] == summary["cutoffs"]
        rate = summary["daily_trend_transitions_fraction"]
        assert rate is None or Decimal(0) <= Decimal(rate) <= Decimal(1)
    assert output["parameters_changed"] is False
    assert output["prospective_oos_admitted"] is False
    assert output["formal_eligibility"] is False
    assert output["portfolio_eligibility"] is None
    assert output["action"] == "no_order"
