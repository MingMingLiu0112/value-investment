"""Frozen quality rule keeps activity distinct from structure and trade admission."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from hotspot_retained_originals import require_retained_originals

from value_investment_agent.domain.hotspot.confirmed_price_structure import analyze_price_behavior
from value_investment_agent.domain.hotspot.current_price import current_signal
from value_investment_agent.domain.hotspot.opportunity_quality import classify_structure


@pytest.mark.parametrize("symbol", ["601318", "300059", "600030"])
def test_completed_real_cases_preserve_negative_evidence(symbol):
    root = Path(__file__).resolve().parents[1]
    paths = list((root / "runtime/hotspot-current-price-cases").glob(f"{symbol}-2026-10-15-*/case.json"))
    if not paths:
        pytest.skip("Local retained negative case absent: " + symbol)
    assert len(paths) == 1
    require_retained_originals(root, paths[0])
    case = json.loads(paths[0].read_text(encoding="utf-8"))
    structures = {period: ("BREAKOUT" if level["breakout_observed"] else
                  "INVALIDATED" if Decimal(level["reference_close"]) < Decimal(level["invalidation_price"]) else
                  "RANGE") for period, level in case["levels"].items()}
    quality = classify_structure(analyze_price_behavior(case["bars"]), structures,
                                 signal_state=current_signal(case["levels"])[0],
                                 trade_date=case["market_trade_date"],
                                 expires_after_session=case["current_reference_close"]["next_session"])
    assert quality["activity_tier"] == "ACTIVE_OBSERVATION"
    assert quality["structure_tier"] != "STRUCTURE_QUALIFIED_OBSERVATION"
    assert quality["expires_after_session"] == case["current_reference_close"]["next_session"]
    assert quality["action"] == case["action"] == "no_order"
    assert quality["formal_eligibility"] is case["action_eligibility"] is False


def test_single_period_trigger_and_downtrend_cannot_be_qualified():
    behavior = dict(action="no_order", daily_trend="UPTREND", observation_quality="RESEARCH_ONLY",
                    structural_invalidation=False, breakout=dict(confirmed_on_next_completed_bar=False),
                    pullback_recovery=dict(observed=False))
    structures = {"daily": "RANGE", "60m": "BREAKOUT", "15m": "BREAKOUT"}
    def classify():
        return classify_structure(behavior, structures, signal_state="TRIGGER_OBSERVED",
                                  trade_date="2026-10-14", expires_after_session="2026-10-15")
    assert classify()["structure_tier"] == "ACTIVE_ONLY"
    behavior["breakout"]["confirmed_on_next_completed_bar"] = True
    assert classify()["structure_tier"] == "STRUCTURE_QUALIFIED_OBSERVATION"
    behavior["daily_trend"] = "DOWNTREND"
    assert classify()["structure_tier"] == "CONFLICT_OR_REJECTED"
    assert "DAILY_DOWNTREND_CONFLICT" in classify()["structure_reasons"]
    behavior["daily_trend"] = "UPTREND"
    structures["60m"] = "INVALIDATED"
    assert classify()["structure_tier"] == "CONFLICT_OR_REJECTED"
    structures["60m"] = "BREAKOUT"
    structures["15m"] = "INVALIDATED"
    assert classify()["structure_tier"] == "CONFLICT_OR_REJECTED"
    assert "SUPPORTING_STRUCTURE_INVALIDATED" in classify()["structure_reasons"]
