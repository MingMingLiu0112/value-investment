"""TEST_ONLY annual financing-dependence arithmetic and temporal boundary."""
from copy import deepcopy

import pytest

from value_investment_agent.application.research.parent_financing_dependency_v1 import (
    assess_parent_financing_dependency,
)


def _compiled():
    row = dict(year=2026, cash_before_distribution_cny="18",
        conditional_distribution_cny="4", cash_policy=dict(
            new_borrowing="10", cash_floor="12"))
    return dict(symbol="TEST_ONLY", valuation_date="2025-12-31", action="no_order",
        scenarios={name: dict(calculation=dict(annual_rows=[deepcopy(row)]))
                   for name in ("bear", "base", "bull")})


def test_model_ledger_quantifies_borrowing_needed_for_floor_and_distribution():
    result = assess_parent_financing_dependency(_compiled())
    row = result["scenarios"]["base"][0]
    assert row["minimum_borrowing_to_preserve_cash_floor_cny"] == "4"
    assert row["minimum_borrowing_to_preserve_modeled_distribution_cny"] == "8"
    assert row["assumed_new_borrowing_cny"] == "10"
    assert row["assumption_dependent"] is True
    assert result["actual_refinancing_capacity_verified"] is False
    assert result["main_valuation_recomputed"] is False
    assert result["action"] == "no_order"


def test_later_unverified_balances_cannot_rebase_historical_model():
    bridge = dict(symbol="TEST_ONLY", period_start="2025-12-31",
                  period_end="2026-06-30", complete_debt_scope_verified=False)
    result = assess_parent_financing_dependency(_compiled(), bridge)
    assert result["followup_observation_date"] == "2026-06-30"
    assert result["followup_rebases_historical_valuation"] is False
    bridge["complete_debt_scope_verified"] = True
    with pytest.raises(ValueError, match="CANNOT_REBASE_MODEL"):
        assess_parent_financing_dependency(_compiled(), bridge)


def test_nonfinite_or_inconsistent_annual_cash_is_rejected():
    value = _compiled()
    value["scenarios"]["bear"]["calculation"]["annual_rows"][0]["cash_before_distribution_cny"] = "NaN"
    with pytest.raises(ValueError, match="NONFINITE"):
        assess_parent_financing_dependency(value)
