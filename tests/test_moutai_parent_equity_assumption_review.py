from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_parent_equity_assumption_review", ROOT / "scripts" / "review_moutai_parent_equity_assumptions.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_assumption_review_keeps_historical_screen_separate_from_admission():
    result = MODULE.build()
    assert Decimal(result["historical_book_growth"]["2020_to_2025_book_value_per_share_cagr"]) > 0
    assert all(Decimal(row["explicit_book_growth_range"][0]) > 0 for row in result["scenario_review"])
    assert all(row["terminal_roe_below_all_observed_ending_equity_profit_ratios"]
               for row in result["scenario_review"])
    assert result["conclusion"] == "historical_anchor_consistent_but_forecast_assumptions_not_independently_validated"
    assert result["valuation_approved"] is False
    assert result["simulation_eligible"] is False
    assert result["trade_approved"] is False


def test_bounded_inverse_does_not_expand_registered_range():
    result = MODULE.bounded_implied_growth(Decimal("150"), lambda g: 100 * (1 + g),
                                          Decimal("-.05"), Decimal(".05"))
    assert result["status"] == "above_registered_envelope"
    assert result["implied_growth"] is None
    result = MODULE.bounded_implied_growth(Decimal("102"), lambda g: 100 * (1 + g),
                                          Decimal("-.05"), Decimal(".05"))
    assert abs(Decimal(result["implied_growth"]) - Decimal(".02")) < Decimal(".000001")


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "Infinity"])
def test_bounded_inverse_rejects_invalid_target(price):
    with pytest.raises(ValueError):
        MODULE.bounded_implied_growth(Decimal(price), lambda g: 100 * (1 + g),
                                      Decimal("-.05"), Decimal(".05"))


def test_current_review_rejects_a_quote_from_a_different_model_session():
    with pytest.raises(ValueError, match="share the reviewed session"):
        MODULE.review_current(ROOT / "runtime/quote-sessions/20260914T105221815291Z/report.json")
