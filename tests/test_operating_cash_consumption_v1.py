"""Direct synthetic mechanism tests; real task replay requires explicit env.

No provider calls, writes, or modification of frozen task evidence.
"""
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal as D
import io
import os
from pathlib import Path
import socket
from unittest.mock import patch

import pytest
import requests

from value_investment_agent.domain.research import operating_cash_consumption_v1 as domain
from value_investment_agent.domain.research.operating_driver_bridge_v1 import build_basis, calculate_path
from value_investment_agent.application.research import operating_cash_consumption_v1 as app


def source_context():
    rows = []
    periods = [
        ("2025-12-31", "FY", ["1200", "360", "120", "60", "36", "24", "600", "120", "456"]),
        ("2025-06-30", "H1", ["500", "150", "50", "25", "15", "10", "250", "50", "190"]),
        ("2026-06-30", "H1", ["400", "135", "40", "20", "12", "8", "200", "40", "152"]),
    ]
    fields = ["revenue", "cost", "surcharges", "selling", "admin", "research",
              "pre_tax_profit", "tax", "parent_profit"]
    for period, basis, values in periods:
        for field, value in zip(fields, values):
            rows.append(dict(id=field+":"+period, field=field, value=value, period=period,
                period_basis=basis, scope="consolidated_parent" if field=="parent_profit" else "consolidated",
                unit="CNY", kind="VERIFIED_REPORTED_FACT", source_id="TEST_ONLY:"+period,
                physical_page=2, pdf_sha256="a"*64, available_at="2026-08-26T00:00:00+00:00"))
    return dict(symbol="000001", action="no_order", evidence=rows)


def row(context, field, period="2026-06-30"):
    return next(r for r in context["evidence"] if r["field"]==field and r["period"]==period)


def bridge_for(context):
    drivers = dict(volume_change=("-0.2", "0.1"), realization_mix_change=("-0.1", "0.05"),
                   unit_cost_change=("0", "0.2"), fixed_cogs_share=("0.2", "0.5"),
                   opex_change=("0", "0.1"), surcharge_ratio=("0.08", "0.12"),
                   other_pretax_cny=("0", "10"))
    inputs = {name: dict(baseline_period="2026-06-30", period_start="2027-01-01",
                        period_end="2027-06-30",
                        drivers={k:dict(lower=a,upper=b) for k,(a,b) in drivers.items()})
              for name in ("bear","base","bull")}
    basis = build_basis(context)
    return dict(action="no_order", inputs=inputs,
                paths={name:calculate_path(basis,p) for name,p in inputs.items()})


@pytest.fixture
def case():
    context = source_context()
    return context, bridge_for(context)


def test_same_period_tax_nci_and_complete_witness_are_consumed(case):
    context, bridge = case
    frozen = deepcopy(bridge)
    result = domain.consume_operating_earnings(context=context, bridge=bridge)
    for name, scenario in result["scenarios"].items():
        assert D(scenario["effective_tax_rate"]) == D(".2")
        assert D(scenario["signed_nci_ratio"]) == D(".05")
        assert len(scenario["anchor_evidence"]) == 3
        for key, witness in scenario["witnesses"].items():
            point = bridge["paths"][name]["extrema"][key]
            assert witness["operating_witness"] == point
            assert D(witness["group_pbt_cny"]) == D(point["pretax_profit_cny"])
            assert D(witness["income_tax_cny"]) == D(witness["group_pbt_cny"]) * D(".2")
    assert bridge == frozen
    assert result["condition_price"] is None and result["main_range_adopted"] is False
    assert result["action"] == "no_order"


def test_negative_signed_nci_is_not_clamped(case):
    context, bridge = case
    row(context, "parent_profit")["value"] = "168"  # group net 160; NCI loss -8
    result = domain.consume_operating_earnings(context=context, bridge=bridge)
    s = result["scenarios"]["base"]
    assert D(s["signed_nci_ratio"]) == D("-.05")
    for witness in s["witnesses"].values():
        assert D(witness["signed_nci_cny"]) < 0
        assert D(witness["parent_profit_cny"]) > D(witness["group_pbt_cny"]) - D(witness["income_tax_cny"])


@pytest.mark.parametrize("fault", ["missing", "duplicate", "unit", "scope", "duration", "source", "period"])
def test_tax_attribution_requires_unique_same_period_anchor(case, fault):
    context, bridge = case
    target = row(context, "tax")
    if fault=="missing": context["evidence"].remove(target)
    elif fault=="duplicate": context["evidence"].append(dict(target,id="duplicate"))
    elif fault=="unit": target["unit"]="USD"
    elif fault=="scope": target["scope"]="parent"
    elif fault=="duration": target["period_basis"]="FY"
    elif fault=="source": row(context,"parent_profit")["source_id"]="OTHER_ORIGINAL"
    else: target["period"]="2025-12-31"
    with pytest.raises(ValueError):
        domain.consume_operating_earnings(context=context, bridge=bridge)


@pytest.mark.parametrize("fault", ["source_value", "witness_amount", "spliced_corner"])
def test_recompute_rejects_source_diff_and_spliced_witness(case, fault):
    context, bridge = case
    if fault=="source_value":
        row(context,"cost")["value"]="136"
    elif fault=="witness_amount":
        bridge["paths"]["base"]["extrema"]["margin_lower"]["pretax_profit_cny"]="999"
    else:
        points=bridge["paths"]["base"]["extrema"]
        assert points["margin_lower"] != points["growth_upper"]
        points["margin_lower"]["revenue_cny"]=points["growth_upper"]["revenue_cny"]
    with pytest.raises(ValueError,match="DIFFERS_FROM_SOURCE_RECOMPUTATION"):
        domain.consume_operating_earnings(context=context,bridge=bridge)


def test_h2_is_fieldwise_fy_minus_h1_then_each_own_trend(case):
    context, bridge = case
    result=domain.build_rolling_income_inputs(context=context,bridge=bridge)
    s=result["scenarios"]["base"]
    expected={"revenue":("700","0.8","560"), "cost":("210","0.9","189"),
              "surcharges":("70","0.8","56"), "selling":("35","0.8","28"),
              "admin":("21","0.8","16.8"), "research":("14","0.8","11.2")}
    for field,(historical,multiplier,projected) in expected.items():
        assert D(s["h2_reported_components"][field])==D(historical)
        assert D(s["h2_transfer_multipliers"][field])==D(multiplier)
        assert D(s["h2_projected_components"][field])==D(projected)
    assert D(s["h2_projected_pbt"])==D("259")
    first=s["annual_income_rows"][0]
    assert D(first["group_pbt_cny"])==D("259")+D(s["d2_witness"]["group_pbt_cny"])
    assert D(first["group_pbt_cny"])!=2*D(s["d2_witness"]["group_pbt_cny"])
    assert s["selected_d2_witness"]=="margin_lower"
    assert s["d2_witness"]["operating_witness"]==bridge["paths"]["base"]["extrema"]["margin_lower"]


def test_ten_continuous_rolling_years_explicit_flat_stress_not_fact(case):
    context, bridge=case
    result=domain.build_rolling_income_inputs(context=context,bridge=bridge)
    assert result["scope"]=="UNADOPTED_STRESS_TRANSPORT_NOT_MAIN_FORECAST"
    for s in result["scenarios"].values():
        years=s["annual_income_rows"]
        assert len(years)==10 and [r["year"] for r in years]==list(range(1,11))
        assert years[0]["period_start"]=="2026-07-01"
        assert years[-1]["period_end"]=="2036-06-30"
        for previous,current in zip(years,years[1:]):
            assert date.fromisoformat(current["period_start"])==date.fromisoformat(previous["period_end"])+timedelta(days=1)
            for field in ("group_pbt_cny","tax_assumption","signed_nci_cny"):
                assert current[field]==previous[field]
        assert s["annual_profit_persistence"]=="EXPLICIT_CONSTANT_OPERATING_INCOME_STRESS_Y2_TO_Y10_NOT_FORECAST"


@pytest.mark.parametrize("fault", ["negative_h2_cost","zero_prior_h1_cost","negative_h2_profit","zero_h2_profit"])
def test_invalid_h2_difference_or_trend_base_rejected(case,fault):
    context,bridge=case
    if fault=="negative_h2_cost":row(context,"cost","2025-12-31")["value"]="149"
    elif fault=="zero_prior_h1_cost":row(context,"cost","2025-06-30")["value"]="0"
    elif fault=="negative_h2_profit":row(context,"pre_tax_profit","2025-12-31")["value"]="249"
    else:row(context,"pre_tax_profit","2025-12-31")["value"]="250"
    with pytest.raises(ValueError):
        domain.build_rolling_income_inputs(context=context,bridge=bridge)


@contextmanager
def no_io_effects():
    original=io.open
    def readonly(file,mode="r",*args,**kwargs):
        assert not any(c in str(mode) for c in "wax+"), "Unexpected write"
        return original(file,mode,*args,**kwargs)
    def denied(*a,**kw):raise AssertionError("Unexpected write/network")
    with patch("io.open",readonly), patch.object(Path,"mkdir",denied), \
         patch.object(Path,"unlink",denied),patch.object(Path,"replace",denied), \
         patch.object(Path,"rename",denied),patch.object(socket.socket,"connect",denied), \
         patch.object(requests.sessions.Session,"request",denied):
        yield


def test_application_rejects_context_recomputation_diff(case,monkeypatch):
    context,bridge=case
    context["snapshot_fingerprint"]="a"*64
    monkeypatch.setattr(app,"build_operating_source_context",lambda **kw:context)
    task=dict(status="SUCCEEDED",scope="LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED",
              symbol="000001",research_as_of="2026-10-31T00:00:00+00:00",
              source_binding={},context_fingerprint="b"*64,operating_driver_bridge=bridge)
    with no_io_effects(),pytest.raises(ValueError,match="OPERATING_CONTEXT_CHANGED"):
        app.read_operating_cash_consumption(root=Path("."),task=task,now=datetime.now(timezone.utc))


def test_issuer_specific_readiness_refuses_600323_cash_followup_without_parent_cash_or_policy(tmp_path, case, monkeypatch):
    """A reported consolidated cash-flow statement is not an E2 cash policy."""
    context,bridge=case
    context.update(symbol="600323", issuer_name="瀚蓝环境股份有限公司", financial_basis="2025-12-31",
                   source_binding={"path":"runtime/TEST_ONLY-600323.json","sha256":"a"*64},
                   snapshot_fingerprint="b"*64)
    (tmp_path/"config").mkdir()
    (tmp_path/"config/current-operating-research-sources-v1.json").write_text(
        '{"schema_version":"current-operating-research-sources-v1","action":"no_order","cases":{}}', encoding="utf-8")
    monkeypatch.setattr(app,"build_operating_source_context",lambda **kwargs:context)
    task=dict(status="SUCCEEDED",scope="LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED",symbol="600323",
              task_id="TEST_ONLY-600323",research_as_of="2026-10-31T00:00:00+00:00",
              source_binding=context["source_binding"],context_fingerprint=context["snapshot_fingerprint"],
              operating_driver_bridge=bridge)
    result=app.read_operating_cash_consumption(root=tmp_path,task=task,now=datetime.now(timezone.utc))
    readiness=result["cash_followup_readiness"]
    assert readiness["status"]=="BLOCKED" and readiness["action"]=="no_order"
    assert readiness["issuer_name"]=="瀚蓝环境股份有限公司"
    assert readiness["cash_followup_registered"] is False
    assert readiness["historical_parent_cash_rows"]==0
    rows={item["code"]:item for item in readiness["missing_evidence"]}
    assert rows["SOURCE_BOUND_CASH_FOLLOWUP_SPEC_REQUIRED"]
    assert rows["PARENT_CASH_FLOW_FACTS_REQUIRED"]["fields"]==["parent_cfo","parent_investment_cash","parent_capex"]
    assert rows["EXPLICIT_SAME_PERIOD_CASH_POLICY_REQUIRED"]
    assert "annual_followup" not in result
    assert result["condition_price"] is None and result["formal_eligibility"] is False


def test_issuer_readiness_preserves_missing_tax_fact_instead_of_raising(tmp_path, case, monkeypatch):
    """D2 success cannot hide an incomplete same-period earnings bridge."""
    context,bridge=case
    context.update(symbol="600323", issuer_name="瀚蓝环境股份有限公司", financial_basis="2025-12-31",
                   source_binding={"path":"runtime/TEST_ONLY-600323.json","sha256":"a"*64},
                   snapshot_fingerprint="b"*64)
    (tmp_path/"config").mkdir()
    (tmp_path/"config/current-operating-research-sources-v1.json").write_text(
        '{"schema_version":"current-operating-research-sources-v1","action":"no_order","cases":{}}', encoding="utf-8")
    monkeypatch.setattr(app,"build_operating_source_context",lambda **kwargs:context)
    monkeypatch.setattr(app,"consume_operating_earnings",lambda **kwargs:(_ for _ in ()).throw(
        ValueError("UNIQUE_REPORTED_FACT_REQUIRED:tax:2025-12-31")))
    task=dict(status="SUCCEEDED",scope="LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED",symbol="600323",
              task_id="TEST_ONLY-600323-tax",research_as_of="2026-10-31T00:00:00+00:00",
              source_binding=context["source_binding"],context_fingerprint=context["snapshot_fingerprint"],
              operating_driver_bridge=bridge)
    result=app.read_operating_cash_consumption(root=tmp_path,task=task,now=datetime.now(timezone.utc))
    assert result["status"]=="UNASSESSABLE" and result["action"]=="no_order"
    rows={item["code"]:item for item in result["cash_followup_readiness"]["missing_evidence"]}
    assert rows["OPERATING_EARNINGS_FACTS_REQUIRED"]["reason"]=="UNIQUE_REPORTED_FACT_REQUIRED:tax:2025-12-31"
    assert result["condition_price"] is None


def test_real_000568_existing_task_consumption_and_rolling_inputs():
    configured=os.environ.get("OPERATING_SOURCES_REAL_ROOT")
    if not configured:pytest.skip("REAL TASK NOT VALIDATED: set OPERATING_SOURCES_REAL_ROOT")
    from value_investment_agent.application.research.agent_review.operating_task_v2 import LiveOperatingTaskService
    from value_investment_agent.application.research.agent_review.operating_sources_v1 import build_operating_source_context
    root=Path(configured).resolve()
    with no_io_effects():
        service=LiveOperatingTaskService(root)
        # _load(recover=False) validates the immutable chain without the public
        # read() lock-file write; re-read the chain after consumption below.
        tasks=[]
        pins={}
        directories=sorted(service.base.glob("rt-*"))
        assert len(directories)<=100
        for directory in directories:
            spec,state,binding=service._load(directory.name,recover=False)
            if spec["symbol"]!="000568":continue
            pins[directory.name]=binding
            tasks.append(service._view(spec,state,binding,datetime.now(timezone.utc)))
        eligible=[t for t in tasks if t.get("status")=="SUCCEEDED" and "operating_driver_bridge" in t]
        assert eligible, "No currently verifiable succeeded driver task; explicit env must not skip"
        task=sorted(eligible,key=lambda t:t["research_as_of"])[-1]
        result=app.read_operating_cash_consumption(root=root,task=task,now=datetime.now(timezone.utc))
        context=build_operating_source_context(root=root,symbol="000568",
            now=datetime.fromisoformat(task["research_as_of"]),binding=task["source_binding"])
        rolling=domain.build_rolling_income_inputs(context=context,bridge=task["operating_driver_bridge"])
        for task_id,binding in pins.items():
            assert service._load(task_id,recover=False)[2]==binding, "Task changed during read-only replay"
    assert result["symbol"]=="000568" and result["condition_price"] is None
    assert result["formal_eligibility"] is False
    assert set(result["scenarios"])=={"bear","base","bull"}
    assert all(len(s["annual_income_rows"])==10 for s in rolling["scenarios"].values())
