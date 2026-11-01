"""Explicit TEST_ONLY fiscal policy cases, never market evidence."""
from copy import deepcopy
from decimal import Decimal as D
import pytest
from value_investment_agent.domain.research.fiscal_distribution_review_v1 import evaluate_fiscal_distribution_policy as evaluate

def inputs():
    base=dict(currency="CNY",scope="consolidated_parent")
    return dict(policy=dict(base,fiscal_year=2026,minimum_payout_ratio=".75",minimum_distribution_cny="850"),
        reported_half=dict(base,period_start="2026-01-01",period_end="2026-06-30",parent_profit_cny="430",kind="REPORTED_FACT"),
        forecast_half=dict(base,period_start="2026-07-01",period_end="2026-12-31",parent_profit_cny="110",kind="FORECAST_ASSUMPTION"))

def test_floor_above_profit_is_not_cash_deficit_or_breach():
    raw=inputs(); before=deepcopy(raw); row=evaluate(**raw)
    assert raw==before
    assert D(row["conditional_fy_parent_profit_cny"])==540
    assert D(row["ratio_target_cny"])==405
    assert D(row["policy_target_cny"])==850
    assert D(row["target_above_current_year_positive_earnings_cny"])==310
    assert row["funding_status"]==row["payment_status"]==row["policy_compliance"]=="NOT_ASSESSED"
    assert not row["formal_eligibility"] and row["condition_price"] is None and row["action"]=="no_order"

def test_ratio_can_dominate_and_negative_profit_does_not_negative_target():
    raw=inputs(); raw["forecast_half"]["parent_profit_cny"]="1570"
    assert D(evaluate(**raw)["policy_target_cny"])==1500
    raw["forecast_half"]["parent_profit_cny"]="-1000"
    assert D(evaluate(**raw)["policy_target_cny"])==850

@pytest.mark.parametrize("part,key,value",[
    ("forecast_half","period_end","2027-06-30"),
    ("forecast_half","period_start","2027-01-01"),
    ("forecast_half","scope","parent_legal"),
    ("reported_half","kind","FORECAST_ASSUMPTION"),
    ("forecast_half","kind","REPORTED_FACT"),
    ("policy","currency","HKD"),
    ("policy","fiscal_year",True),
    ("policy","minimum_payout_ratio","1.1"),
    ("policy","minimum_distribution_cny","-1"),
    ("forecast_half","parent_profit_cny","NaN"),
    ("forecast_half","parent_profit_cny",True),
])
def test_wrong_period_scope_type_or_amount_refuses(part,key,value):
    raw=inputs(); raw[part][key]=value
    with pytest.raises(ValueError):evaluate(**raw)

def test_prior_year_paid_amount_cannot_be_credited():
    raw=inputs(); raw["reported_half"]["prior_year_dividend_paid_cny"]="850"
    with pytest.raises(ValueError):evaluate(**raw)
