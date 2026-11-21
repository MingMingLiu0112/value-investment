"""Check the fixed half-year payment convention and the shared F1 constraints."""
from datetime import date
from decimal import Decimal, localcontext

import pytest

from value_investment_agent.domain.valuation.direct_parent_half_year_cash_v1 import (
    value_parent_half_year_cash,
)
from value_investment_agent.domain.valuation.direct_parent_owner_cash_v1 import FLOW_KEYS, SCOPE


def cash_inputs():
    def flow(profit):
        return dict(dict.fromkeys(FLOW_KEYS, "0"), parent_profit=profit,
                    operating_cash=profit, payout_ratio="1")

    return dict(
        valuation_date=date(2026, 6, 30),
        first_period_start=date(2026, 7, 1),
        first_period_end=date(2026, 12, 31),
        opening=dict(book="1000", cash="0", debt="0", capacity="0"),
        years=[dict(year=2026, policy=flow("40"), scheduled_owner_distribution_cny="0")],
        terminal=dict(policy=flow("80"), rationale="TEST_ONLY stationary",
                      remaining_scheduled_events=[], max_transition_years=3),
        ordinary_shares="10", cost_of_equity="0.08", scope=SCOPE, currency="CNY",
    )


def test_half_year_cash_uses_dated_stub_and_terminal():
    result = value_parent_half_year_cash(**cash_inputs())
    row, = result["annual_rows"]
    assert row["payment_date"] == result["terminal_value_date"] == "2026-12-31"
    assert result["action"] == "no_order"
    with localcontext() as ctx:
        ctx.prec = 48
        elapsed = Decimal(184) / 365
        factor = Decimal("1.08") ** elapsed
        assert abs(Decimal(row["discount_years"]) - elapsed) < Decimal("1e-46")
        assert abs(Decimal(result["conditional_equity_value_cny"]) - 1040 / factor) < Decimal("1e-40")
        assert abs(Decimal(row["equity_charge_cny"]) - 1000 * (factor - 1)) < Decimal("1e-40")
        assert abs(Decimal(result["crosscheck_difference_cny"])) < Decimal("1e-40")


def test_half_year_cash_rejects_whole_year_input_and_preserves_funding_constraint():
    inputs = cash_inputs()
    with pytest.raises(ValueError, match="DIRECT_OWNER_H2_EXPLICIT_STUB_PERIOD_REQUIRED"):
        value_parent_half_year_cash(**dict(inputs, first_period_start=date(2026, 1, 1)))
    inputs["years"][0]["policy"]["other_mandatory_cash"] = "41"
    with pytest.raises(ValueError, match="DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2026"):
        value_parent_half_year_cash(**inputs)

def test_declared_distribution_floor_is_checked_on_actual_payout():
    assert value_parent_half_year_cash(
        **cash_inputs(), minimum_distribution_by_year={2026: "40"}
    )["minimum_distribution_by_year"] == {2026: "40"}
    with pytest.raises(ValueError, match="DISTRIBUTION_BELOW_DECLARED_FLOOR:2026"):
        value_parent_half_year_cash(**cash_inputs(), minimum_distribution_by_year={2026: "41"})
    with pytest.raises(ValueError, match="DISTRIBUTION_FLOOR_YEARS_INVALID"):
        value_parent_half_year_cash(**cash_inputs(), minimum_distribution_by_year={2027: "40"})
