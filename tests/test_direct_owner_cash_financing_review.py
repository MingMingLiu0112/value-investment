"""TEST_ONLY arithmetic boundaries for the public financing stress view."""
from value_investment_agent.application.product.direct_owner_cash_view_v1 import (
    _first_year_no_new_borrowing_stress,
    _opening_debt_evidence_comparison,
)


def test_no_new_borrowing_stress_preserves_cash_floor_and_zero_distribution():
    row = dict(
        year=2026,
        cash_before_distribution_cny="18856840911.11",
        cash_policy=dict(new_borrowing="60000000000", cash_floor="13404587376.75"),
    )
    stress = _first_year_no_new_borrowing_stress([row])
    assert stress["removed_assumed_new_borrowing_cny"] == "60000000000"
    assert stress["cash_before_distribution_without_new_borrowing_cny"] == "-41143159088.89"
    assert stress["minimum_funding_gap_to_cash_floor_cny"] == "54547746465.64"
    assert stress["year"] == 2026


def test_no_new_borrowing_with_enough_internal_cash_has_no_gap():
    row = dict(
        year=2026,
        cash_before_distribution_cny="200",
        cash_policy=dict(new_borrowing="50", cash_floor="100"),
    )
    assert _first_year_no_new_borrowing_stress([row])["minimum_funding_gap_to_cash_floor_cny"] == "0"
    assert _first_year_no_new_borrowing_stress([]) is None


def test_opening_debt_comparison_keeps_identified_lines_separate_from_assumption():
    keys=("short_term_borrowings_cny", "current_noncurrent_liabilities_cny",
          "long_term_borrowings_cny", "lease_liabilities_cny")
    balance={key: dict(current=str(index), classification="FACT", currency="CNY",
                       scope="ISSUER_PARENT_STANDALONE",
                       source_refs={"current_period": "2025-12-31", "field": key})
             for index, key in enumerate(keys, start=1)}
    compiled=dict(valuation_date="2025-12-31", opening={"debt": "60"},
                  evidence={"statements": [{"balance_sheet": balance}]})
    review=_opening_debt_evidence_comparison(compiled)
    assert review["identified_parent_balance_lines_cny"] == "10"
    assert review["unexplained_difference_cny"] == "50"
    assert review["completeness_verified"] is False
    assert review["maturity_schedule_verified"] is False
    balance[keys[0]]["source_refs"]["current_period"]="2026-06-30"
    assert _opening_debt_evidence_comparison(compiled) is None
