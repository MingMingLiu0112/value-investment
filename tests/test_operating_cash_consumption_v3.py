"""Synthetic source/response integration, never real company acceptance."""
from copy import deepcopy
from datetime import timedelta
import json
import pytest
from test_operating_horizon_draft_v1 import context, payload, NOW
from value_investment_agent.application.research.agent_review import operating_horizon_draft_v1 as draft
from value_investment_agent.application.research.agent_review import operating_horizon_task_v1 as service
from value_investment_agent.application.research import operating_cash_consumption_v3 as mod


def test_supplement_reuses_earnings_and_annual_compiler_without_cash_invention(context,monkeypatch,tmp_path):
    research=draft.validate_response(json.dumps(payload([2026,2027])),context,[2026,2027],NOW)
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
    assert set(out["years"])=={"2026","2027"}
    assert out["years"]["2026"]["scenarios"]["base"]["model_year"]==1
    assert out["years"]["2027"]["scenarios"]["base"]["model_year"]==2
    assert out["cash_model_ready"] is False and out["condition_price"] is None
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


def test_latest_failure_does_not_silently_restore_old_success(monkeypatch,tmp_path):
    tasks=[dict(task_id="old",created_at="2026-11-01",status="SUCCEEDED"),
           dict(task_id="new",created_at=NOW.isoformat(),updated_at=NOW.isoformat(),research_as_of=NOW.isoformat(),execution_mode="LIVE_OPERATING",status="FAILED",record_binding={},error_code="TEST_ONLY")]
    monkeypatch.setattr(service.OperatingHorizonTaskService,"list_for_symbol",lambda self,symbol:tasks)
    out=mod.read_annual_supplement(root=tmp_path,symbol="123456",now=NOW)
    assert out["task_id"]=="new" and out["status"]=="FAILED" and out["years"]=={}
