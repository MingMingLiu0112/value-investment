"""TEST_ONLY nine-stage D1 task on existing immutable store and shared ledger."""
import json
from datetime import datetime, timezone

import pytest

from value_investment_agent.application.research.agent_review import parent_cash_task_v2 as target
from value_investment_agent.application.research import direct_owner_cash_staged_v2 as staged
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse

NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)
CFG = dict(model_id="deepseek-flash", max_completion_tokens_cap=4096,
    input_cost_per_million="1", output_cost_per_million="1",
    max_run_cost="1", daily_cost_limit="2", currency="CNY")


def term(count):
    return dict(values=["1.25"] * count, evidence_anchors=["profit"],
        mechanism="Explicit parent cash mechanism", counter_evidence="Sales or debt may change",
        reopen_condition="Reopen on new official filing")


class Provider:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def complete(self, request):
        packet = json.loads(request.user)
        self.calls.append((packet["scenario"], packet["stage"]))
        if len(self.calls) == self.fail_at:
            raise TimeoutError("ambiguous transport")
        fields = packet["required_fields"]
        if packet["stage"] == "terminal":
            body = dict(terminal=dict(policy={key: term(1) for key in fields},
                remaining_scheduled_events=[], max_transition_years=10, financing=None,
                rationale="Terminal cash mechanism", counter_evidence="Debt may change",
                reopen_condition="Reopen on new filing"), cost_of_equity=term(1))
        else:
            body = dict(years=packet["required_years"],
                series={key: term(10) for key in fields})
            if packet["stage"] == "operating":
                body.update(annual_notes=["Annual cash driver rationale"] * 10,
                    rationale="Scenario parent cash rationale",
                    counter_evidence="Cash conversion may weaken",
                    reopen_condition="Reopen on new parent filing")
        return LLMResponse(json.dumps(body), 100, 100, "deepseek-flash")


@pytest.fixture
def task(tmp_path, monkeypatch):
    context = dict(input_fingerprint="a" * 64, symbol="600887",
        valuation_date="2025-12-31", facts={"profit": {"period_end": "2025-12-31"},
        "revenue": {"period_end": "2025-12-31"}})
    monkeypatch.setattr(target, "model_configuration", lambda root: CFG.copy())
    monkeypatch.setattr(target, "read_parent_cash_agent_facts", lambda **_: context)
    monkeypatch.setattr(staged, "read_parent_cash_agent_facts", lambda **_: context)
    monkeypatch.setattr(target, "assemble_parent_cash_drafts", lambda **_:
        dict(action="no_order", formal_eligibility=False, main_range_adopted=False))
    provider = Provider()
    return target.ParentCashTaskServiceV2(tmp_path, test_provider=provider), provider


def test_nine_stages_and_shared_budget(task):
    service, provider = task
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashv2001", now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "SUCCEEDED", result.get("error_code")
    assert result["completed_scenarios"] == ["base", "bear", "bull"]
    assert result["completed_stages"] == list(target.STAGE_ORDER)
    assert len(provider.calls) == 9 and result["provider_requests"] == 9
    assert result["candidate"]["action"] == "no_order"
    assert result["formal_eligibility"] is False
    assert service.read(created["task_id"])["status"] == "SUCCEEDED"
    assert len(provider.calls) == 9


def test_ambiguous_stage_never_resends(task):
    service, provider = task
    provider.fail_at = 2
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashv2002", now=NOW)
    failed = service.run(created["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["error_code"].startswith("BEAR_POLICY_PARENT_PROVIDER_TIMEOUT")
    assert failed["completed_stages"] == ["bear.operating"]
    assert service.resume(created["task_id"], now=NOW)["status"] == "FAILED"
    assert len(provider.calls) == 2


def test_model_cash_alias_is_rejected_after_response_is_sealed(task):
    service, _ = task
    class AliasingProvider(Provider):
        def complete(self, request):
            response = super().complete(request)
            body = json.loads(response.text)
            body["series"]["operating_cash"] = body["series"].pop("other_operating_cash")
            return LLMResponse(json.dumps(body), 100, 100, "deepseek-flash")
    service.test_provider = AliasingProvider()
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashv2003", now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "BEAR_OPERATING_PARENT_V2_YEARS_OR_SERIES_INVALID"
    assert result["completed_stages"] == []
    assert result["settled_cost"] != "0"
    assert service.resume(created["task_id"], now=NOW)["status"] == "FAILED"


def test_economic_rejection_keeps_all_raw_responses(task, monkeypatch):
    service, provider = task
    monkeypatch.setattr(target, "assemble_parent_cash_drafts", lambda **_:
                        (_ for _ in ()).throw(ValueError("DIRECT_OWNER_UNCONSUMED_FUTURE_EVENTS")))
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashv2004", now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "PARENT_V2_ECONOMIC_DIRECT_OWNER_UNCONSUMED_FUTURE_EVENTS"
    assert len(provider.calls) == 9
    assert len(result["returned_responses"]) == 9
    assert "candidate" not in result


def test_budget_head_tamper_invalidates_completed_view(task):
    service, _ = task
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashv2005", now=NOW)
    result = service.run(created["task_id"], now=NOW)
    day = next(iter(result["reservations"].values()))["day"]
    (service.daily.base / "budget" / day / "current.json").write_text("{}", encoding="utf-8")
    reopened = service.read(created["task_id"])
    assert reopened["status"] == "FAILED"
    assert reopened["error_code"] == "PARENT_SOURCE_OR_CHECKPOINT_INVALID"
