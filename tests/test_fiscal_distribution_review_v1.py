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

def update_case():
    from value_investment_agent.domain.research.fiscal_distribution_review_v1 import compare_fiscal_projection_with_nine_months
    projection=evaluate(**inputs())
    update=dict(status="VERIFIED",period_basis="YEAR_TO_DATE_9M_NOT_SINGLE_QUARTER",
        period_start="2026-01-01",period_end="2026-09-30",
        fields=dict(parent_profit_cny=dict(value="567",unit="CNY",scope="consolidated_parent",
            physical_page=2,excerpt="TEST_ONLY")))
    return compare_fiscal_projection_with_nine_months,projection,update

def test_new_ytd_exceeding_frozen_projection_implies_loss_not_actual_or_revised_value():
    compare,projection,update=update_case()
    before=deepcopy(projection)
    result=compare(fiscal_review=projection,ytd_update=update)
    assert result["implied_q4_parent_profit_cny"]=="-27"
    assert result["implication"]=="IMPLIED_Q4_LOSS_REQUIRES_EXPLICIT_REVIEW"
    assert result["value_classification"]=="DERIVED_CONDITIONAL_IMPLICATION_NOT_REPORTED_Q4_OR_NEW_FORECAST"
    assert result["model_revalidated"] is False and result["condition_price"] is None
    assert projection==before and result["source_anchor"]==update["fields"]["parent_profit_cny"]

@pytest.mark.parametrize("field,value",[
    ("period_start","2025-01-01"),("period_end","2025-09-30"),
    ("period_basis","SINGLE_QUARTER"),("status","UNKNOWN")])
def test_nine_month_update_cannot_mix_fiscal_year_or_single_quarter(field,value):
    compare,projection,update=update_case();update[field]=value
    with pytest.raises(ValueError):compare(fiscal_review=projection,ytd_update=update)

def test_group_profit_not_parent_profit_and_unknown_amount_refuse():
    compare,projection,update=update_case()
    update["fields"]["parent_profit_cny"]["scope"]="consolidated"
    with pytest.raises(ValueError):compare(fiscal_review=projection,ytd_update=update)
    update["fields"]["parent_profit_cny"].update(scope="consolidated_parent",value="UNKNOWN")
    with pytest.raises(ValueError):compare(fiscal_review=projection,ytd_update=update)
