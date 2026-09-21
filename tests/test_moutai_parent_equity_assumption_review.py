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


def test_current_review_reproduces_model_without_changing_admission():
    result = MODULE.review_current(ROOT / "runtime/quote-sessions/20260914T105221815291Z/report.json")
    assert result["arithmetic_reproduced"] is True
    assert result["reviewed_as_of"].startswith("2026-09-14")
    assert result["quote_price_cny"] == "1277.96"
    assert len(result["profit_paths"]) == 3
    assert [row["fade_years"] for row in result["reverse_valuation"]] == [0, 5, 10]
    assert all(row["implied_growth"] is None for row in result["reverse_valuation"])
    assert result["simulation_eligible"] is False
    assert result["trade_approved"] is False
