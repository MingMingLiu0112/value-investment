"""V18 cash candidate and sealed-source offline regression tests."""
import json
from types import SimpleNamespace

import pytest

from test_operating_horizon_task_v10_live import task, NOW
from test_operating_horizon_draft_v1 import context as base_context
from test_operating_horizon_split_v8 import split_context, _annual, _cash
from value_investment_agent.application.research.agent_review import operating_horizon_task_v16_live as v16
from value_investment_agent.application.research.agent_review import operating_horizon_task_v17_cash as v17
from value_investment_agent.application.research.agent_review import operating_horizon_task_v18_cash as v18
from value_investment_agent.application.research.agent_review import operating_horizon_request_v18_cash as request
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


def _failed_source(task):
    old, _, _ = task
    calls = []
    def complete(req):
        calls.append(req)
        data = json.loads(_annual())
        year = data["years"]["2027"]
        for path in year["operating_paths"].values():
            path["unit_cost_case"]["mechanism"] = "采购价格随合同和原料市场变化而调整，单位成本可能变化，需核对同口径成本。"
        for name in ("counter_evidence", "reopen_condition"):
            year["operating_paths"][name] = year.pop(name)
        return LLMResponse(json.dumps(data, ensure_ascii=False), 100, 5000, "TEST_ONLY")
    service = v16.OperatingHorizonTaskService(old.root,
        source_loader=old.source_loader, source_loader_version=old.source_loader_version,
        test_provider=SimpleNamespace(complete=complete))
    queued = service.create(symbol="600519", request_key="V18_SOURCE_ANNUAL", years=[2027], now=NOW)
    failed = service.run(queued["task_id"], now=NOW)
    assert failed["error_code"] == "V16_ANNUAL_RESPONSE_REJECTED"
    return service, queued["task_id"], calls


def test_v18_contract_request_and_replay(task):
    source, source_id, calls = _failed_source(task)
    cash_calls = []
    def complete(req):
        cash_calls.append(req)
        return LLMResponse(_cash(unknown=True), 100, 50, "TEST_ONLY")
    service = v18.OperatingHorizonTaskService(source.root, source_service=source,
        test_provider=SimpleNamespace(complete=complete))
    queued = service.create_imported(source_task_id=source_id, request_key="V18_CASH_RESEARCH", now=NOW)
    spec, _, _ = service._load(queued["task_id"])
    assert spec["task_contract"] == v18.CONTRACT != v17.CONTRACT
    assert service.base != v17.OperatingHorizonTaskService(source.root,
        source_service=source, test_provider=service.test_provider).base
    request_obj = service._replay(spec)[4]
    assert request.VERSION in request_obj.system
    ledger = json.loads(request_obj.user.split("TERM_CANDIDATE_IDS=")[1])
    assert set(ledger) == set(request.full.TERMS)
    assert all(len(ids) <= 2 for ids in ledger.values())
    assert "no_order" == spec["action"] and spec["cash_request_sha256"]
    result = service.run(queued["task_id"], now=NOW)
    assert result["provider_requests"] == len(cash_calls) == 1
    assert result["status"] in {"SUCCEEDED", "WAITING_EVIDENCE"}
    assert service.read(queued["task_id"])["provider_requests"] == 1
    assert len(calls) == 1


def test_v18_request_hash_and_source_tamper(task):
    source, source_id, _ = _failed_source(task)
    service = v18.OperatingHorizonTaskService(source.root, source_service=source,
        test_provider=SimpleNamespace(complete=lambda req: pytest.fail("provider called")))
    queued = service.create_imported(source_task_id=source_id, request_key="V18_HASH_CHECK", now=NOW)
    spec, _, _ = service._load(queued["task_id"])
    with pytest.raises(ValueError, match="V18_CASH_REQUEST_CHANGED"):
        service._replay({**spec, "cash_request_sha256": "0" * 64})
    packet = source._directory(source_id) / "response-annual.json"
    packet.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Task binding hash mismatch"):
        service.read(queued["task_id"])


def test_v18_numeric_requires_term_candidate(task):
    _, context, _ = task
    from value_investment_agent.application.research.agent_review import operating_horizon_split_v13 as split
    projected = split._project(context, context["source_binding"])
    data = json.loads(_cash(unknown=True))
    item = data["years"]["2027"]["shareholder_cash_paths"]["base"]["commitment_cash_cny"]
    item.update(classification="FORECAST_ASSUMPTION", value="1", rationale="Mechanism: conditional historical bridge")
    with pytest.raises(ValueError, match="V18_NUMERIC_TERM_LACKS_HISTORICAL_CANDIDATE"):
        request.validate_response(json.dumps(data), context, context["source_binding"])







def test_v18_numeric_candidate_is_conditional_only(task):
    _, context, _ = task
    data = json.loads(_cash(unknown=True))
    item = data["years"]["2027"]["shareholder_cash_paths"]["base"]["accessible_profit_ratio"]
    item.update(classification="FORECAST_ASSUMPTION", value="0.5",
                evidence_ids=["test:pre_tax_profit"],
                rationale="Mechanism: FY2025 historical profit is a contestable scenario anchor, not a 2027 fact; cash scope could differ and later filings can overturn it.")
    assert request.validate_response(json.dumps(data), context, context["source_binding"]) is True
    item["evidence_ids"] = ["test:cost"]
    with pytest.raises(ValueError, match="V18_NUMERIC_TERM_LACKS_HISTORICAL_CANDIDATE"):
        request.validate_response(json.dumps(data), context, context["source_binding"])


def test_v18_mock_provider_rejects_unanchored_numeric_after_settlement(task):
    source, source_id, _ = _failed_source(task)
    bad = json.loads(_cash(unknown=True))
    item = bad["years"]["2027"]["shareholder_cash_paths"]["base"]["commitment_cash_cny"]
    item.update(classification="FORECAST_ASSUMPTION", value="1",
                rationale="Mechanism: unverified 2027 commitment condition", evidence_ids=["test:revenue"])
    calls = []
    def complete(req):
        calls.append(req)
        return LLMResponse(json.dumps(bad), 100, 50, "TEST_ONLY")
    service = v18.OperatingHorizonTaskService(source.root, source_service=source,
        test_provider=SimpleNamespace(complete=complete))
    queued = service.create_imported(source_task_id=source_id, request_key="V18_BAD_NUMERIC", now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "V18_CASH_RESPONSE_REJECTED"
    assert result["provider_requests"] == len(calls) == 1
    assert result["settled_cost"] != "0"
    assert service.resume(queued["task_id"], now=NOW)["provider_requests"] == 1


def test_v18_live_requires_exact_v9_loader(task):
    old, _, _ = task
    source = v16.OperatingHorizonTaskService(old.root,
        source_loader=old.source_loader, source_loader_version=old.source_loader_version,
        test_provider=SimpleNamespace(complete=lambda req: pytest.fail("provider called")))
    with pytest.raises(ValueError, match="V18_EXACT_V9_SOURCE_LOADER_REQUIRED"):
        v18.OperatingHorizonTaskService(source.root, source_service=source)
