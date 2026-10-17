from decimal import Decimal
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

from value_investment_agent.domain.hotspot.confirmed_price_structure import (
    RULE_VERSION, SWING_SIDE_BARS, RETEST_LOOKBACK, confirmed_swings, analyze_price_behavior,
    conditional_action_rules,
)
from value_investment_agent.domain.hotspot.price_action_plan import calculate_price_levels


def rows(values):
    return [dict(time=f"2026-09-{i + 1:02d}", open=str(value), close=str(value),
                 high=str(Decimal(str(value)) + 1), low=str(Decimal(str(value)) - 1),
                 volume="100", amount="1000") for i, value in enumerate(values)]


def test_swing_is_only_known_after_both_right_bars_complete():
    data = rows([10, 11, 12, 11, 10, 11, 13, 12, 11])
    assert not any(point["pivot_at"] == data[6]["time"] for point in confirmed_swings(data[:8], period="daily"))
    point = next(point for point in confirmed_swings(data, period="daily") if point["pivot_at"] == data[6]["time"])
    assert point["known_at"] == data[8]["time"]


def test_insufficient_confirmed_structure_and_no_target_fail_closed():
    data = rows([10, 11, 12, 13, 14, 15, 16, 17])
    output = analyze_price_behavior({period: data for period in ("daily", "60m", "15m")})
    assert output["daily_trend"] == "UNKNOWN"
    assert output["risk_reward_ratio"] is None
    assert output["formal_eligibility"] is False


def test_future_append_cannot_rewrite_prior_swing_known_at():
    data = rows([10, 11, 12, 11, 10, 11, 13, 12, 11])
    before = confirmed_swings(data, period="daily")
    extended = data + [dict(data[-1], time="2026-09-10", open="12", close="12", high="13", low="11")]
    after = confirmed_swings(extended, period="daily")
    assert all(point in after for point in before)


def minute_rows(count):
    clocks = ("10:30:00", "11:30:00", "14:00:00", "15:00:00")
    start = datetime(2026, 9, 22)
    return [dict(time=f"{(start + timedelta(days=i // 4)).date()} {clocks[i % 4]}",
                 open="10", close="10", high="11", low="9", volume="100", amount="1000")
            for i in range(count)]


def analyze_minutes(minutes, daily=None):
    return analyze_price_behavior({
        "daily": daily or rows([10, 11, 12, 11, 10, 11, 13, 12, 11]),
        "60m": minutes, "15m": minute_rows(8),
    })


def retest_rows(following_count=1):
    data = minute_rows(6 + following_count + 1)
    data[5].update(open="10", close="12", high="13", low="10", volume="200")
    for row in data[6:-1]:
        row.update(open="11.5", close="11.5", high="12", low="11.1", volume="80")
    data[6]["low"] = "10.9"
    data[-1].update(open="11.5", close="12.5", high="13", low="11", volume="200")
    return data


def test_breakout_confirmation_uses_previous_frozen_level_not_current_rolling_level():
    data = minute_rows(7)
    data[5].update(close="12", high="13", low="10", volume="200")
    data[6].update(open="12", close="12", high="12", low="11")
    before = analyze_minutes(data[:6])
    after = analyze_minutes(data)
    assert before["breakout"]["observed"] is True
    assert before["breakout"]["confirmed_on_next_completed_bar"] is False
    assert before["breakout"]["level"] == "11"
    assert after["breakout"]["confirmed_on_next_completed_bar"] is True
    assert after["breakout"]["observed"] is False
    # The currently exposed level belongs to today's rolling window, not the
    # prior confirmed breakout. Review handoff calls out this evidence gap.
    assert after["breakout"]["level"] == "13"
    assert after["breakout"]["confirmation_level"] == "11"
    assert after["breakout"]["breakout_at"] == data[-2]["time"]
    assert after["breakout"]["confirmed_at"] == data[-1]["time"]


@pytest.mark.parametrize("close,confirmed", [("11", False), ("11.01", True), ("10.99", False)])
def test_confirmation_boundary_is_currently_strictly_above_frozen_level(close, confirmed):
    data = minute_rows(7)
    data[5].update(close="12", high="13", low="10", volume="200")
    data[6].update(open=close, close=close, high="12", low="10")
    assert analyze_minutes(data)["breakout"]["confirmed_on_next_completed_bar"] is confirmed


def test_retest_recovery_appears_only_after_final_completed_prefix():
    data = retest_rows()
    before = analyze_minutes(data[:-1])
    after = analyze_minutes(data)
    assert before["pullback_recovery"]["observed"] is False
    assert after["pullback_recovery"]["observed"] is True
    evidence = after["pullback_recovery"]["evidence"]
    assert evidence["level"] == "11"
    assert evidence["breakout_at"] == data[5]["time"]
    assert evidence["confirmed_at"] == data[-1]["time"]
    assert evidence["contracted_touch_count"] == 1


@pytest.mark.parametrize("mutation", ["close_below", "no_touch", "not_contracted", "no_recovery", "no_volume"])
def test_retest_requires_all_registered_conditions(mutation):
    data = retest_rows()
    if mutation == "close_below":
        data[6].update(close="10.9", low="10.8")
    elif mutation == "no_touch":
        data[6]["low"] = "11.1"
    elif mutation == "not_contracted":
        data[6]["volume"] = "200"
    elif mutation == "no_recovery":
        data[-1]["close"] = "12"
    elif mutation == "no_volume":
        data[-1]["volume"] = "100"
    assert analyze_minutes(data)["pullback_recovery"]["observed"] is False


@pytest.mark.parametrize("interim_bars,observed", [(9, True), (10, False)])
def test_retest_lookback_boundary_is_ten_bars_not_eleven(interim_bars, observed):
    data = retest_rows(interim_bars)
    assert analyze_minutes(data)["pullback_recovery"]["observed"] is observed


def test_upper_target_cannot_reach_back_beyond_latest_two_confirmed_highs():
    daily = rows([10, 11, 19, 11, 10, 9, 10, 12, 10, 9, 8, 9, 11, 9, 8, 7, 8])
    highs = [point for point in confirmed_swings(daily, period="daily") if point["kind"] == "HIGH"]
    assert [point["price"] for point in highs] == ["20", "13", "12"]
    minutes = minute_rows(8)
    for row in minutes:
        row["high"] = "14"
    output = analyze_minutes(minutes, daily)
    assert output["nearest_confirmed_upper_resistance"] is None
    assert output["risk_reward_ratio"] is None
    assert output["formal_eligibility"] is False


def test_registration_constants_match_and_do_not_grant_admission():
    root = Path(__file__).resolve().parents[1]
    registration = json.loads((root / "config/hotspot-confirmed-structure-v1.json").read_text(encoding="utf-8"))
    assert registration["rule_version"] == RULE_VERSION
    assert registration["swing_left_bars"] == registration["swing_right_bars"] == SWING_SIDE_BARS
    assert registration["retest_lookback_bars"] == RETEST_LOOKBACK
    assert registration["parameter_optimization"] is False
    assert registration["formal_eligibility"] is False
    assert registration["action"] == "no_order"


def rules_for(minutes, daily=None):
    return conditional_action_rules(analyze_minutes(minutes, daily),
                                    calculate_price_levels(minutes, period="60m"))


def test_conditional_add_requires_completed_recovery_and_uses_frozen_level():
    data = retest_rows()
    before, after = rules_for(data[:-1]), rules_for(data)
    assert before["ADD"]["observed"] is False and before["ADD"]["price"] is None
    assert after["ADD"]["observed"] is True and after["ADD"]["price"] == "11"
    for intent, rule in after.items():
        assert rule["requires_existing_holding"] is (intent != "OPEN")
        assert rule["rule"] and rule["status"] == "CONDITIONAL_REVIEW_ONLY"
        assert rule["formal_eligibility"] is rule["personal_permission"] is False
        assert rule["action"] == "no_order"


@pytest.mark.parametrize("close,volume,opened,exited", [
    ("11", "120", False, False), ("11.01", "120", True, False),
    ("11.01", "119.99", False, False), ("9", "100", False, False),
    ("8.99", "100", False, True),
])
def test_conditional_open_exit_preserve_strict_price_and_volume_boundaries(close, volume, opened, exited):
    data = minute_rows(6)
    data[-1].update(open=close, close=close, high="12", low="8", volume=volume)
    rules = rules_for(data)
    assert rules["OPEN"]["observed"] is opened
    assert rules["EXIT"]["observed"] is exited


def test_conditional_reduce_reuses_existing_downtrend_without_invented_price():
    daily = rows([15, 16, 18, 16, 15, 13, 15, 17, 15, 14, 12, 14, 15])
    behavior = analyze_minutes(minute_rows(8), daily)
    assert behavior["daily_trend"] == "DOWNTREND"
    rule = rules_for(minute_rows(8), daily)["REDUCE"]
    assert rule["observed"] is True and rule["price"] is None
    assert analyze_minutes(minute_rows(8))["observation_quality"] == "INSUFFICIENT_UPPER_SPACE"
    assert rules_for(minute_rows(8))["REDUCE"]["observed"] is True
    assert rules_for(minute_rows(8), rows([10, 11, 12, 13, 14, 15]))["REDUCE"]["observed"] is False
