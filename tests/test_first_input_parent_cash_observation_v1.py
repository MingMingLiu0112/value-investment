"""TEST_ONLY arithmetic and fail-closed contract; no retained runtime sources."""
import pytest

from value_investment_agent.application.research.first_input_parent_cash_observation_v1 import (
    FLOWS, calculate_ttm_flows,
)


def _period(name, cfo, capex, closing):
    flows = {field: "10.00" for field in FLOWS}
    flows.update(cfo_cny=cfo, gross_capex_cny=capex)
    return dict(period=name, flows=flows,
                closing_cash_and_equivalents_cny=closing)


def test_ttm_is_interval_flows_only():
    periods = [
        _period("FY2025", "7150459122.43", "631984543.41", "900.00"),
        _period("H12025", "-2890913995.51", "237582482.91", "800.00"),
        _period("H12026", "35551654301.69", "1235902972.58", "700.00"),
    ]
    result = calculate_ttm_flows(periods)
    assert result["cfo_cny"] == "45593027419.63"
    assert result["gross_capex_cny"] == "1630305033.08"
    assert "closing_cash_and_equivalents_cny" not in result
    assert result["mixed_distribution_interest_paid_cny"] == "10.00"


def test_missing_flow_fails_instead_of_zero():
    periods = [_period(p, "1.00", "2.00", "3.00")
               for p in ("FY2025", "H12025", "H12026")]
    del periods[1]["flows"]["debt_repaid_cny"]
    with pytest.raises(KeyError):
        calculate_ttm_flows(periods)
