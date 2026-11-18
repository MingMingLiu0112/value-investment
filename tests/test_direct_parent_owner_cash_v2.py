"""TEST_ONLY V2 owner-distribution arithmetic; no investment approval."""

from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from value_investment_agent.domain.valuation.direct_parent_owner_cash_v1 import (
    compile_direct_owner_cash_path as compile_v1,
)
from value_investment_agent.domain.valuation.direct_parent_owner_cash_v2 import (
    compile_direct_owner_cash_path,
    compile_direct_owner_cash_path_v2,
)


def v1_inputs():
    policy = dict(
        parent_profit="80",
        operating_cash="100",
        investment_cash_received="0",
        maintenance_capex="20",
        growth_capex="0",
        commitments_outside_capex="0",
        debt_repayment="0",
        new_borrowing="0",
        interest_outside_cfo="0",
        other_mandatory_cash="0",
        cash_floor="20",
        payout_ratio="1",
        reserve_ratio="0",
    )
    return dict(
        opening=dict(book="1000", cash="20", capacity="0", debt="0"),
        years=[dict(year=2027, policy=deepcopy(policy))],
        terminal=dict(
            policy=deepcopy(policy),
            remaining_scheduled_events=[],
            rationale="TEST_ONLY unchanged profit and gross maintenance forever",
            max_transition_years=100,
        ),
        ordinary_shares="100",
        cost_of_equity="0.08",
        scope="ISSUER_PARENT_STANDALONE",
        currency="CNY",
    )


def v2_inputs(*, scheduled="0"):
    data = v1_inputs()
    data["years"] = [
        dict(
            year=row["year"],
            policy=deepcopy(row["policy"]),
            scheduled_owner_distribution_cny=scheduled,
        )
        for row in data["years"]
    ]
    return data


def test_scheduled_distribution_consumes_cash_and_capacity_before_conditional():
    data = v2_inputs(scheduled="30")
    data["years"][0]["policy"]["payout_ratio"] = "0.5"
    row = compile_direct_owner_cash_path_v2(**data)["annual_rows"][0]

    assert Decimal(row["scheduled_owner_distribution_cny"]) == 30
    assert Decimal(row["conditional_distribution_cny"]) == 40
    assert Decimal(row["total_owner_distribution_cny"]) == 70
    assert Decimal(row["dividend_assumption_cny"]) == 70
    assert Decimal(row["closing_cash_cny"]) == 30
    assert Decimal(row["closing_distribution_capacity_cny"]) == 10
    assert Decimal(row["closing_book_equity_cny"]) == 1010


def test_scheduled_distribution_refuses_insufficient_nonborrowed_cash():
    data = v2_inputs(scheduled="81")
    data["opening"]["capacity"] = "100"
    with pytest.raises(ValueError, match="REQUIRES_BORROWING_OR_CASH:2027"):
        compile_direct_owner_cash_path_v2(**data)


def test_scheduled_distribution_cannot_be_manufactured_by_new_borrowing():
    data = v2_inputs(scheduled="1")
    data["opening"].update(cash="20", capacity="100")
    data["years"][0]["policy"].update(
        operating_cash="20", maintenance_capex="20", new_borrowing="100"
    )
    with pytest.raises(ValueError, match="REQUIRES_BORROWING_OR_CASH:2027"):
        compile_direct_owner_cash_path_v2(**data)


def test_scheduled_distribution_refuses_insufficient_capacity():
    data = v2_inputs(scheduled="41")
    data["opening"].update(cash="100", capacity="0")
    data["years"][0]["policy"]["reserve_ratio"] = "0.5"
    with pytest.raises(ValueError, match="EXCEEDS_CAPACITY:2027"):
        compile_direct_owner_cash_path_v2(**data)


@pytest.mark.parametrize("location", ["terminal", "terminal_policy"])
def test_terminal_refuses_any_scheduled_distribution_field(location):
    data = v2_inputs()
    if location == "terminal":
        data["terminal"]["scheduled_owner_distribution_cny"] = "0"
    else:
        data["terminal"]["policy"]["scheduled_owner_distribution_cny"] = "0"
    with pytest.raises(ValueError, match="NOT_ALLOWED_IN_TERMINAL"):
        compile_direct_owner_cash_path_v2(**data)


def test_zero_scheduled_is_economically_identical_to_v1():
    old = compile_v1(**v1_inputs())
    new = compile_direct_owner_cash_path_v2(**v2_inputs())

    for key in (
        "terminal_equity_value_cny",
        "terminal_steady_distribution_cny",
        "conditional_equity_value_cny",
        "per_share_value",
        "dividend_crosscheck_equity_value_cny",
        "residual_income_equity_value_cny",
        "crosscheck_difference_cny",
    ):
        assert Decimal(new[key]) == Decimal(old[key])
    for old_row, new_row in zip(old["annual_rows"], new["annual_rows"], strict=True):
        for key in (
            "opening_book_equity_cny",
            "net_income_assumption_cny",
            "residual_income_cny",
            "closing_book_equity_cny",
            "conditional_distribution_cny",
            "closing_cash_cny",
            "closing_distribution_capacity_cny",
        ):
            assert Decimal(new_row[key]) == Decimal(old_row[key])
        assert Decimal(new_row["scheduled_owner_distribution_cny"]) == 0
        assert Decimal(new_row["total_owner_distribution_cny"]) == Decimal(
            old_row["conditional_distribution_cny"]
        )
    assert all(
        Decimal(row["scheduled_owner_distribution_cny"]) == 0
        for row in new["terminal_rows"]
    )


def test_zero_scheduled_preserves_v1_borrowing_cash_floor_semantics():
    old_data = v1_inputs()
    old_data["opening"].update(cash="0", debt="20")
    old_data["years"][0]["policy"].update(
        operating_cash="40",
        maintenance_capex="20",
        debt_repayment="20",
        new_borrowing="20",
    )
    old_data["terminal"]["policy"].update(
        debt_repayment="20", new_borrowing="20", interest_outside_cfo="20"
    )
    old_data["terminal"]["financing"] = {
        "mode": "CONSTANT_DEBT_REFINANCING",
        "rationale": "TEST_ONLY equal principal rollover",
        "counter_evidence": "TEST_ONLY refinancing may be unavailable",
        "reopen_condition": "TEST_ONLY debt policy changes",
        "coverage": {
            "interest_outside_cfo": True,
            "debt_scope": "ALL_EXISTING_TERMINAL_DEBT",
        },
    }
    new_data = deepcopy(old_data)
    new_data["years"] = [
        dict(
            year=2027,
            policy=deepcopy(old_data["years"][0]["policy"]),
            scheduled_owner_distribution_cny="0",
        )
    ]
    # The explicit zero must not add a stricter finite-year borrowing rule.
    assert Decimal(
        compile_direct_owner_cash_path(**new_data)["annual_rows"][0][
            "total_owner_distribution_cny"
        ]
    ) == Decimal(
        compile_v1(**old_data)["annual_rows"][0]["conditional_distribution_cny"]
    )


def test_distribution_above_current_profit_keeps_clean_surplus_and_ri_exact():
    data = v2_inputs(scheduled="100")
    data["opening"].update(cash="200", capacity="200")
    result = compile_direct_owner_cash_path_v2(**data)
    row = result["annual_rows"][0]

    assert Decimal(row["conditional_distribution_cny"]) == 80
    assert Decimal(row["total_owner_distribution_cny"]) == 180
    assert Decimal(row["closing_book_equity_cny"]) == 900
    assert Decimal(row["retention_assumption"]) == Decimal("-1.25")
    assert Decimal(row["residual_income_cny"]) == 0
    assert abs(Decimal(result["crosscheck_difference_cny"])) < Decimal("1e-30")


@pytest.mark.parametrize("scheduled", ["-1", True, 1.0, "NaN", "Infinity"])
def test_scheduled_distribution_requires_nonnegative_finite_decimal(scheduled):
    data = v2_inputs(scheduled=scheduled)
    with pytest.raises(ValueError):
        compile_direct_owner_cash_path_v2(**data)


def test_v1_regression_contract_remains_unchanged():
    result = compile_v1(**v1_inputs())
    assert result["schema_version"] == "direct-parent-owner-cash-v1"
    assert Decimal(result["conditional_equity_value_cny"]) == 1000
    assert result["annual_rows"][0]["conditional_distribution_cny"] == "80"
    assert "scheduled_owner_distribution_cny" not in result["annual_rows"][0]
    assert result["formal_eligibility"] is False
    assert result["action"] == "no_order"


def test_v2_is_context_independent_and_permanently_no_order():
    expected = compile_direct_owner_cash_path_v2(**v2_inputs(scheduled="10"))
    with localcontext() as context:
        context.prec = 5
        assert compile_direct_owner_cash_path_v2(**v2_inputs(scheduled="10")) == expected
        assert context.prec == 5
    assert expected["formal_eligibility"] is False
    assert expected["action"] == "no_order"
