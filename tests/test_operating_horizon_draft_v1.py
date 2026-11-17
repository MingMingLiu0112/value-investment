"""Synthetic contract tests; not real research or provider acceptance."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import pytest
from value_investment_agent.application.research.agent_review import operating_horizon_draft_v1 as mod

NOW = datetime(2026, 11, 5, 4, tzinfo=timezone.utc)

@pytest.fixture
def context():
    values = dict(revenue="1000", cost="500", surcharges="10", selling="10", admin="20", research="5", pre_tax_profit="455")
    return dict(symbol="123456",issuer_name="TEST_ONLY",as_of="2026-11-05",snapshot_fingerprint="a"*64,
        evidence=[dict(id="test:"+k,source_id="TEST_ONLY",pdf_sha256="b"*64,
            available_at="2026-04-01T00:00:00+00:00",period="2025-12-31",period_basis="FY",
            scope="consolidated",unit="CNY",field=k,value=v,text="TEST_ONLY reported row") for k,v in values.items()])


def payload(years):
    result={}
    for y in years:
        drivers={k:dict(lower="0",upper="0",rationale="TEST_ONLY fixed assumption",evidence_ids=["test:revenue"]) for k in mod.bridge.DRIVERS}
        drivers["surcharge_ratio"].update(lower="0.01",upper="0.01")
        drivers["realization_mix_change"].update(lower=str((y-2025)/100),upper=str((y-2025)/100))
        path=dict(baseline_period="2025-12-31",period_start=f"{y}-01-01",period_end=f"{y}-12-31",drivers=drivers,
            capital_assumptions=[dict(dimension=d,period_start=f"{y}-01-01",period_end=f"{y}-12-31",
                classification="UNKNOWN",lower=None,upper=None,unit="not_quantified",rationale="TEST_ONLY unavailable",
                evidence_ids=["test:revenue"]) for d in mod.prior.CAPITAL])
        result[str(y)]=dict(estimate_kind="CURRENT_FY_ESTIMATE" if y==2026 else "FUTURE_FY_ASSUMPTION",
            operating_paths={s:deepcopy(path) for s in mod.prior.SCENARIOS},counter_evidence="TEST_ONLY contract expiry",
            reopen_condition="TEST_ONLY signed renewal changes revenue scope")
    return dict(years=result)


def test_current_year_is_estimate_and_future_years_use_independent_inputs(context):
    out=mod.validate_response(json.dumps(payload([2026,2027])),context,[2026,2027],NOW)
    a=out["years"]["2026"]["calculated_paths"]["base"]
    b=out["years"]["2027"]["calculated_paths"]["base"]
    assert a["extrema"]["growth_lower"]["revenue_cny"]=="1010.00"
    assert b["extrema"]["growth_lower"]["revenue_cny"]=="1020.00" # not 1010 * 1.02
    assert out["years"]["2026"]["estimate_kind"]=="CURRENT_FY_ESTIMATE"
    assert out["formal_eligibility"] is False and out["valuation_produced"] is False
    assert out["years"]["2026"]["operating_paths"]["base"]["capital_assumptions"][0]["lower"] is None

@pytest.mark.parametrize("years",[[2025],[2026,2026],[2027,2026],[2036],[True],[],[2026,2027,2028,2029]])
def test_invalid_years(context,years):
    with pytest.raises(ValueError):mod.build_request(context,years)

@pytest.mark.parametrize("mutation,match",[
    (lambda p:p["years"]["2026"].update(estimate_kind="FACT"),"CANNOT_BECOME_ACTUAL"),
    (lambda p:p["years"]["2026"]["operating_paths"]["base"].update(period_start="2027-01-01"),"CALENDAR"),
    (lambda p:p["years"]["2026"]["operating_paths"]["base"]["drivers"]["volume_change"].update(evidence_ids=["fabricated"]),"CITATION"),
    (lambda p:p["years"]["2026"]["operating_paths"]["base"]["capital_assumptions"][0].update(lower="0"),"MUST_REMAIN_NULL"),
    (lambda p:p["years"]["2026"]["operating_paths"]["base"]["drivers"]["volume_change"].update(lower="NaN"),"FINITE"),
    (lambda p:p["years"]["2026"].update(counter_evidence=""),"nonempty"),
])
def test_false_evidence_and_bad_economic_inputs_rejected(context,mutation,match):
    p=payload([2026]);mutation(p)
    with pytest.raises(ValueError,match=match):mod.validate_response(json.dumps(p),context,[2026],NOW)


def test_missing_year_and_future_source_rejected(context):
    with pytest.raises(ValueError):mod.validate_response(json.dumps(payload([2027])),context,[2026,2027],NOW)
    context["evidence"][0]["available_at"]="2027-01-01T00:00:00+00:00"
    with pytest.raises(ValueError,match="future"):mod.build_request(context,[2026])


def test_request_citations_and_calendar_are_explicit(context):
    request=mod.build_request(context,[2026])
    assert "CURRENT_FY_ESTIMATE" in request.user
    path=request.output_schema["properties"]["years"]["properties"]["2026"]["properties"]["operating_paths"]["properties"]["base"]
    assert path["properties"]["period_start"]["const"]=="2026-01-01"
    assert "test:revenue" in path["properties"]["drivers"]["properties"]["volume_change"]["properties"]["evidence_ids"]["items"]["enum"]


def test_shanghai_midnight_generation_time(context):
    made=datetime(2026,11,4,16,30,tzinfo=timezone.utc)
    assert mod.validate_response(json.dumps(payload([2026])),context,[2026],made)["action"]=="no_order"
    with pytest.raises(ValueError,match="GENERATION_TIME"):
        mod.validate_response(json.dumps(payload([2026])),context,[2026],made.replace(hour=15))
