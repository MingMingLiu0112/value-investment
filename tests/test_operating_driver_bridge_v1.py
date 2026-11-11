from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from value_investment_agent.domain.research.operating_driver_bridge_v1 import (
    build_basis, calculate_path, build_thresholds, evaluate_condition, DRIVERS)

def context():
    rows = []
    for period, basis, revenue in (("2024-12-31","FY","800"),("2025-12-31","FY","1000"),
                                    ("2025-06-30","H1","500"),("2026-06-30","H1","400")):
        values = dict(revenue=revenue,cost="400",surcharges="100",selling="60",
                      admin="30",research="10",pre_tax_profit="450")
        for field,value in values.items():
            rows.append(dict(id=field+":"+period,field=field,period=period,period_basis=basis,
                             scope="consolidated",unit="CNY",value=value))
    return dict(evidence=rows)

def path(baseline="2025-12-31", end="2026-12-31"):
    points=dict(volume_change="0",realization_mix_change="0",unit_cost_change="0",
                fixed_cogs_share=".25",opex_change="0",surcharge_ratio=".1",other_pretax_cny="50")
    return dict(baseline_period=baseline,period_start=end[:4]+"-01-01",period_end=end,
                drivers={k:dict(lower=v,upper=v) for k,v in points.items()})

def test_zero_shock_reconstructs_reported_pretax_not_normalized():
    result=calculate_path(build_basis(context()),path())
    case=result["extrema"]["margin_lower"]
    assert case["revenue_cny"]=="1000.00"
    assert case["cogs_cny"]=="400.00" and case["opex_cny"]=="100.00"
    assert case["pretax_profit_cny"]=="450.00"
    assert result["margin_range"]==dict(lower="0.45",upper="0.45")
    assert result["corner_count"]==128 and result["formal_eligibility"] is False

def test_volume_mix_costs_actually_transmit_into_profit():
    p=path()
    for key,value in dict(volume_change="-.1",realization_mix_change=".05",
                          unit_cost_change=".1",opex_change="-.02").items():
        p["drivers"][key]=dict(lower=value,upper=value)
    r=calculate_path(build_basis(context()),p)
    case=r["extrema"]["margin_lower"]
    assert case["revenue_cny"]=="945.00" and case["cogs_cny"]=="407.00"
    assert case["opex_cny"]=="98.00" and case["surcharges_cny"]=="94.50"
    assert case["pretax_profit_cny"]=="395.50"
    assert Decimal(r["growth_range"]["lower"])==Decimal("-.055")

def test_same_period_comparisons_never_mix_fy_and_half_year():
    r=build_basis(context())
    comparisons=[x for x in r["comparisons"] if x["field"]=="revenue"]
    assert [(x["current_period"],x["prior_period"],Decimal(x["change_ratio"])) for x in comparisons]==[
        ("2025-12-31","2024-12-31",Decimal(".25")),
        ("2026-06-30","2025-06-30",Decimal("-.2"))]

@pytest.mark.parametrize("fault",["missing","duplicate","scope","unit","basis","zero"])
def test_bad_original_basis_does_not_get_a_synthetic_baseline(fault):
    c=context(); row=next(x for x in c["evidence"] if x["id"]=="revenue:2025-12-31")
    if fault=="missing":c["evidence"].remove(row)
    elif fault=="duplicate":c["evidence"].append(dict(row,id="other"))
    elif fault=="scope":row["scope"]="parent"
    elif fault=="unit":row["unit"]="USD"
    elif fault=="basis":row.pop("period_basis")
    else:row["value"]="0"
    assert "2025-12-31" not in build_basis(c)["baselines"]

def test_forecast_must_match_baseline_reporting_length():
    with pytest.raises(ValueError,match="PERIOD_MISMATCH"):
        calculate_path(build_basis(context()),path("2026-06-30","2027-12-31"))
    r=calculate_path(build_basis(context()),path("2025-12-31","2027-12-31"))
    assert r["comparison_basis"]=="CUMULATIVE_RELATIVE_TO_BASELINE_NOT_YOY"

@pytest.mark.parametrize("driver,value",[
    ("volume_change","-1"),("realization_mix_change","-1"),("unit_cost_change","-1.01"),
    ("opex_change","-1.01"),("fixed_cogs_share","1.1"),("surcharge_ratio","NaN")])
def test_invalid_driver_domain_rejected(driver,value):
    p=path();p["drivers"][driver]=dict(lower=value,upper=value)
    with pytest.raises(ValueError):calculate_path(build_basis(context()),p)

def test_threshold_equals_edge_and_historical_baseline_cross_is_not_reopen():
    result=calculate_path(build_basis(context()),path())
    result["margin_range"]=dict(lower="0.55",upper="0.585")
    condition=next(x for x in build_thresholds({"bull":result})
                   if x["metric"]=="pretax_margin" and x["direction"]=="ABOVE")
    observation={k:condition[k] for k in ("metric","period_start","period_end","period_basis","scope","baseline_period","comparison_basis")}
    observation.update(value="0.58",available_at="2027-01-10T00:00:00+00:00")
    now=datetime(2027,1,11,tzinfo=timezone.utc)
    assert evaluate_condition(condition,observation,observed_at=now)["status"]=="WITHIN_CONDITION"
    observation["value"]="0.585"
    assert evaluate_condition(condition,observation,observed_at=now)["status"]=="WITHIN_CONDITION"
    observation["value"]="0.586"
    assert evaluate_condition(condition,observation,observed_at=now)["status"]=="REOPEN_RESEARCH"
    observation["scope"]="parent"
    assert evaluate_condition(condition,observation,observed_at=now)["status"]=="NOT_ASSESSABLE"

@pytest.mark.parametrize("end",["2024-12-31","2025-12-31"])
def test_no_future_or_contemporaneous_baseline_in_forecast(end):
    with pytest.raises(ValueError,match="FORECAST_MUST_FOLLOW_BASELINE"):
        calculate_path(build_basis(context()),path("2025-12-31",end))

def test_yoy_observation_cannot_trigger_cumulative_condition():
    r=calculate_path(build_basis(context()),path("2025-12-31","2027-12-31"))
    c=build_thresholds({"base":r})[0]
    observation={k:c[k] for k in ("metric","period_start","period_end","period_basis","scope","baseline_period","comparison_basis")}
    observation.update(value="-0.8",available_at="2028-01-10T00:00:00+00:00",
                       comparison_basis="PROJECTED_YOY_SAME_PERIOD")
    assert evaluate_condition(c,observation,observed_at=datetime(2028,1,11,tzinfo=timezone.utc))["status"]=="NOT_ASSESSABLE"
