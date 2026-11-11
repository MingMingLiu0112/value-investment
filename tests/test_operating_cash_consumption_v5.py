"""Synthetic source/response integration, never real company acceptance."""
from copy import deepcopy
from datetime import timedelta
import json
import pytest
from test_operating_horizon_draft_v1 import context, payload, NOW
from value_investment_agent.application.research.agent_review import operating_horizon_draft_v2 as draft
from value_investment_agent.application.research.agent_review import operating_horizon_task_v1 as service_v1
from value_investment_agent.application.research.agent_review import operating_horizon_task_v2 as service_v2
from value_investment_agent.application.research.agent_review import operating_horizon_task_v3 as service
from value_investment_agent.application.research import operating_cash_consumption_v5 as mod


def test_supplement_reuses_earnings_and_annual_compiler_without_cash_invention(context,monkeypatch,tmp_path):
    raw=payload([2026,2027])
    for year in raw["years"].values():
        for path in year["operating_paths"].values():
            path["unit_cost_mechanism"]="UNRESOLVED_SENSITIVITY"
            path["drivers"]["other_pretax_cny"]["evidence_ids"]=["test:pre_tax_profit"]
    research=draft.validate_response(json.dumps(raw),context,[2026,2027],NOW)
    full=deepcopy(context)
    full.update(action="no_order",financial_basis="2025-12-31")
    template=deepcopy(full["evidence"][0])
    for field,value,scope in [("tax","91","consolidated"),("parent_profit","350","consolidated_parent")]:
        full["evidence"].append(dict(template,id="test:"+field,field=field,value=value,scope=scope))
    for row in full["evidence"]:row.update(kind="VERIFIED_REPORTED_FACT",physical_page=1)
    task=dict(task_id="TEST_ONLY",created_at=NOW.isoformat(),status="SUCCEEDED",record_binding={},
        source_binding={},research_as_of=NOW.isoformat(),updated_at=NOW.isoformat(),execution_mode="LIVE_OPERATING",context_fingerprint=full["snapshot_fingerprint"],research_result=research)
    monkeypatch.setattr(service.OperatingHorizonTaskService,"list_for_symbol",lambda self,symbol:[task])
    monkeypatch.setattr(mod,"build_operating_source_context",lambda **kw:full)
    out=mod.read_annual_supplement(root=tmp_path,symbol="123456",now=NOW)
    assert out["years"]["2026"]["unit_cost_mechanisms"]["base"]=="UNRESOLVED_SENSITIVITY"
    assert out["years"]["2026"]["quantification_status"].startswith("CONDITIONAL_SENSITIVITY")
    assert set(out["years"])=={"2026","2027"}
    assert out["years"]["2026"]["scenarios"]["base"]["model_year"]==1
    assert out["years"]["2027"]["scenarios"]["base"]["model_year"]==2
    assert out["cash_model_ready"] is False and out["condition_price"] is None
    assert out["scope_decomposition_status"]=="SCOPE_CHANGE_APPLICABILITY_NOT_DECLARED"
    assert out["years"]["2026"]["earnings"]["base"]["shareholder_distribution"] is None
    task["execution_mode"]="TEST_ONLY_LIVE_CONTRACT"
    assert mod.read_annual_supplement(root=tmp_path,symbol="123456",now=NOW)["status"]=="TEST_ONLY_NOT_REAL_RESEARCH"
    task["execution_mode"]="LIVE_OPERATING"
    with pytest.raises(ValueError,match="TASK_AFTER"):
        mod.read_annual_supplement(root=tmp_path,symbol="123456",now=NOW-timedelta(seconds=1))
    research["generated_at"]=(NOW+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError,match="RESPONSE_AFTER"):
        mod.read_annual_supplement(root=tmp_path,symbol="123456",now=NOW)
    research["generated_at"]=NOW.isoformat()
    task["context_fingerprint"]="changed"
    with pytest.raises(ValueError,match="SOURCE_CONTEXT_CHANGED"):
        mod.read_annual_supplement(root=tmp_path,symbol="123456",now=NOW)


def test_regular_d2_consumes_source_bound_scope_assessment_not_model_output(context,monkeypatch,tmp_path):
    raw=payload([2026])
    for path in raw["years"]["2026"]["operating_paths"].values():
        path["unit_cost_mechanism"]="UNRESOLVED_SENSITIVITY"
        path["drivers"]["other_pretax_cny"]["evidence_ids"]=["test:pre_tax_profit"]
    research=draft.validate_response(json.dumps(raw),context,[2026],NOW)
    full=deepcopy(context)
    full.update(action="no_order",financial_basis="2025-12-31")
    template=deepcopy(full["evidence"][0])
    for field,value,scope in [("tax","91","consolidated"),("parent_profit","350","consolidated_parent")]:
        full["evidence"].append(dict(template,id="test:"+field,field=field,value=value,scope=scope))
    for row in full["evidence"]: row.update(kind="VERIFIED_REPORTED_FACT",physical_page=1)
    full["scope_decomposition"]={
        "scope_change_expected":False,
        "contributions":[{"scope_kind":"LEGACY_ORGANIC","revenue_change_cny":"10",
            "profit_change_cny":"2","evidence_ids":[full["evidence"][0]["id"]]}],
    }
    task=dict(task_id="TEST_ONLY",created_at=NOW.isoformat(),status="SUCCEEDED",record_binding={},
        source_binding={},research_as_of=NOW.isoformat(),updated_at=NOW.isoformat(),execution_mode="LIVE_OPERATING",
        context_fingerprint=full["snapshot_fingerprint"],research_result=research)
    monkeypatch.setattr(service.OperatingHorizonTaskService,"list_for_symbol",lambda self,symbol:[task])
    monkeypatch.setattr(mod,"build_operating_source_context",lambda **kw:full)
    assert mod.read_annual_supplement(root=tmp_path,symbol="123456",now=NOW)["scope_decomposition_status"]=="STABLE_SCOPE_VERIFIED"
    full["scope_decomposition"]["scope_change_expected"]=True
    with pytest.raises(ValueError,match="NEW_SCOPE_BRIDGE_REQUIRED"):
        mod.read_annual_supplement(root=tmp_path,symbol="123456",now=NOW)


def test_latest_failure_does_not_silently_restore_old_success(monkeypatch,tmp_path):
    tasks=[dict(task_id="old",created_at="2026-11-01",status="SUCCEEDED"),
           dict(task_id="new",created_at=NOW.isoformat(),updated_at=NOW.isoformat(),research_as_of=NOW.isoformat(),execution_mode="LIVE_OPERATING",status="FAILED",record_binding={},error_code="TEST_ONLY")]
    monkeypatch.setattr(service.OperatingHorizonTaskService,"list_for_symbol",lambda self,symbol:tasks)
    out=mod.read_annual_supplement(root=tmp_path,symbol="123456",now=NOW)
    assert out["task_id"]=="new" and out["status"]=="FAILED" and out["years"]=={}


def test_current_v1_task_is_consumed_even_when_historical_v3_repair_exists(monkeypatch,tmp_path):
    historical = dict(task_id="historical-repair", created_at="2026-11-01T00:00:00+00:00",
        updated_at="2026-11-01T00:00:00+00:00", research_as_of="2026-11-01T00:00:00+00:00",
        execution_mode="LIVE_OPERATING", status="FAILED", record_binding={}, error_code="HISTORICAL")
    current = dict(task_id="current-v1", created_at=NOW.isoformat(), updated_at=NOW.isoformat(),
        research_as_of=NOW.isoformat(), execution_mode="LIVE_OPERATING", status="FAILED",
        record_binding={}, error_code="CURRENT")
    monkeypatch.setattr(service_v1.OperatingHorizonTaskService,"list_for_symbol",lambda self,symbol:[current])
    monkeypatch.setattr(service_v2.OperatingHorizonTaskService,"list_for_symbol",lambda self,symbol:[])
    monkeypatch.setattr(service.OperatingHorizonTaskService,"list_for_symbol",lambda self,symbol:[historical])
    out=mod.read_annual_supplement(root=tmp_path,symbol="123456",now=NOW)
    assert out["task_id"]=="current-v1" and out["reason"]=="CURRENT"


def test_admitted_v1_draft_is_explicitly_not_promoted_to_e2_without_cost_mechanisms(monkeypatch,tmp_path,context):
    from value_investment_agent.application.research.agent_review import operating_horizon_draft_v1 as draft_v1
    raw=payload([2026])
    research=draft_v1.validate_response(json.dumps(raw),context,[2026],NOW)
    task=dict(task_id="current-v1",created_at=NOW.isoformat(),updated_at=NOW.isoformat(),
        research_as_of=NOW.isoformat(),execution_mode="LIVE_OPERATING",status="SUCCEEDED",
        record_binding={},source_binding={},context_fingerprint=context["snapshot_fingerprint"],research_result=research)
    monkeypatch.setattr(mod,"_registered_horizon_tasks",lambda **kwargs:[task])
    monkeypatch.setattr(mod,"build_operating_source_context",lambda **kwargs:context)
    out=mod.read_annual_supplement(root=tmp_path,symbol="123456",now=NOW)
    assert out["status"]=="D2_DRAFT_CONTRACT_NOT_E2_COMPATIBLE"
    assert out["reason"]=="UNIT_COST_MECHANISM_CONTRACT_REQUIRED"
    assert out["years"]=={} and out["action"]=="no_order"


def test_repair_projection_preserves_both_older_generations(monkeypatch,tmp_path):
    from value_investment_agent.application.research import operating_cash_consumption_v4
    old={"historical_annual_research_supplement":{"task_id":"v1"},"annual_research_supplement":{"task_id":"v2"},"consumption_fingerprint":"old"}
    monkeypatch.setattr(operating_cash_consumption_v4,"read_operating_cash_consumption",lambda **kwargs:deepcopy(old))
    monkeypatch.setattr(mod,"read_annual_supplement",lambda **kwargs:{"status":"FAILED","task_id":"v3"})
    out=mod.read_operating_cash_consumption(root=tmp_path,task={"symbol":"123456"},now=NOW)
    assert [x["task_id"] for x in out["annual_research_supplement_history"]]==["v1","v2"]
    assert out["annual_research_supplement"]["task_id"]=="v3"
