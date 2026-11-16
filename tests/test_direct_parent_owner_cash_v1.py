"""TEST_ONLY positive/negative economic contracts; no real-company approval."""
from copy import deepcopy
from decimal import Decimal, localcontext
import pytest
from value_investment_agent.domain.valuation.direct_parent_owner_cash_v1 import compile_direct_owner_cash_path


def inputs():
    policy=dict(parent_profit="80",operating_cash="100",investment_cash_received="0",
        maintenance_capex="20",growth_capex="0",commitments_outside_capex="0",
        debt_repayment="0",new_borrowing="0",interest_outside_cfo="0",
        other_mandatory_cash="0",cash_floor="20",payout_ratio="1",reserve_ratio="0")
    return dict(opening=dict(book="1000",cash="20",capacity="0",debt="0"),
        years=[dict(year=2027,policy=deepcopy(policy))],
        terminal=dict(policy=deepcopy(policy),remaining_scheduled_events=[],
                      rationale="TEST_ONLY unchanged profit and gross maintenance forever",
                      max_transition_years=100),ordinary_shares="100",
        cost_of_equity="0.08",scope="ISSUER_PARENT_STANDALONE",currency="CNY")


def test_perpetual_80_distributed_at_8_percent_equals_1000_and_shared_equity_matches():
    result=compile_direct_owner_cash_path(**inputs())
    assert Decimal(result["conditional_equity_value_cny"])==1000
    assert abs(Decimal(result["crosscheck_difference_cny"]))<Decimal("1e-30")
    assert result["annual_rows"][0]["conditional_distribution_cny"]=="80"
    assert result["annual_rows"][0]["closing_cash_cny"]=="20"
    assert result["working_capital_cash_component"] is None
    assert not result["legal_distribution_capacity_certified"]


def test_positive_profit_does_not_create_cash_or_terminal_funding():
    data=inputs()
    data["years"][0]["policy"]["operating_cash"]="10"
    with pytest.raises(ValueError,match="UNFUNDED"):
        compile_direct_owner_cash_path(**data)


def test_actual_annual_cash_limits_payout_and_changes_retention():
    data=inputs()
    data["years"][0]["policy"]["operating_cash"]="50"
    row=compile_direct_owner_cash_path(**data)["annual_rows"][0]
    assert Decimal(row["conditional_distribution_cny"])==30
    assert Decimal(row["closing_book_equity_cny"])==1050
    assert Decimal(row["retention_assumption"])==Decimal("0.625")


def test_debt_repayment_and_investment_receipts_are_separate_from_cfo():
    data=inputs()
    data["opening"]["debt"]="30"
    data["years"][0]["policy"].update(debt_repayment="30",investment_cash_received="10")
    row=compile_direct_owner_cash_path(**data)["annual_rows"][0]
    assert Decimal(row["conditional_distribution_cny"])==60
    assert row["closing_debt_cny"]=="0"


@pytest.mark.parametrize("change,reason",[
    ("unknown","Explicit finite"),
    ("double_wc","EXACT_FIELDS"),
    ("remaining_event","UNCONSUMED"),
    ("debt","TERMINAL_DEBT"),
    ("bad_terminal","STATIONARY"),
    ("wrong_scope","PARENT_CNY"),
    ("missing_year","NONCONTIGUOUS"),
])
def test_unsupported_contracts_refuse(change,reason):
    data=inputs()
    if change=="unknown":data["years"][0]["policy"]["maintenance_capex"]=None
    if change=="double_wc":data["years"][0]["policy"]["operating_wc_cash_cny"]="0"
    if change=="remaining_event":data["terminal"]["remaining_scheduled_events"]=[2030]
    if change=="debt":data["opening"]["debt"]="1"
    if change=="bad_terminal":data["terminal"]["policy"]["operating_cash"]="200"
    if change=="wrong_scope":data["scope"]="CONSOLIDATED"
    if change=="missing_year":data["years"].append(dict(year=2029,policy=data["years"][0]["policy"]))
    with pytest.raises(ValueError,match=reason):compile_direct_owner_cash_path(**data)


def test_terminal_continuing_capex_is_not_reset_to_zero():
    data=inputs()
    data["terminal"]["policy"]["maintenance_capex"]="50"
    result=compile_direct_owner_cash_path(**data)
    assert Decimal(result["terminal_steady_distribution_cny"])==50
    assert Decimal(result["conditional_equity_value_cny"])<1000
    assert result["terminal_rows"][0]["cash_policy"]["maintenance_capex"]=="50"


def test_decimal_context_does_not_change_cash_equity_or_value():
    data=inputs()
    expected=compile_direct_owner_cash_path(**data)
    with localcontext() as ctx:
        ctx.prec=5
        assert compile_direct_owner_cash_path(**data)==expected
        assert ctx.prec==5
