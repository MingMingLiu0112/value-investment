"""Direct D1 parent-cash execution tests; all provider calls are local mocks."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from value_investment_agent.application.research.agent_review import parent_cash_task_v1 as target
from value_investment_agent.infrastructure.agent_runtime.provider import LLMRequest, LLMResponse


NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)
CFG = dict(model_id="deepseek-flash", max_completion_tokens_cap=4096,
    input_cost_per_million="1", output_cost_per_million="1",
    max_run_cost="1", daily_cost_limit="2", currency="CNY")


class Provider:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def complete(self, request):
        self.calls.append(request.user)
        if len(self.calls) == self.fail_at:
            raise TimeoutError("ambiguous transport outcome")
        return LLMResponse(request.user, 10, 10, "deepseek-flash")


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(target, "model_configuration", lambda root: CFG.copy())
    monkeypatch.setattr(target, "read_parent_cash_agent_facts", lambda **kwargs:
        dict(input_fingerprint="a" * 64))
    monkeypatch.setattr(target, "parent_cash_request", lambda **kwargs:
        LLMRequest("FUNDAMENTAL", "source only", kwargs["scenario"], {}, 1024))
    monkeypatch.setattr(target, "parse_parent_cash_response", lambda response, *, scenario,
        source_fingerprint: {"scenario": scenario, "source_fingerprint": source_fingerprint})
    monkeypatch.setattr(target, "assemble_parent_cash_drafts", lambda **kwargs:
        dict(action="no_order", formal_eligibility=False, scenarios=sorted(kwargs["drafts"])))
    provider = Provider()
    instance = target.ParentCashTaskService(tmp_path, test_provider=provider)
    return instance, provider


def test_three_stages_and_shared_budget(service):
    task, provider = service
    created = task.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
                          request_key="parentcash001", now=NOW)
    result = task.run(created["task_id"], now=NOW)
    assert result["status"] == "SUCCEEDED"
    assert task._load(created["task_id"])[0]["config"]["max_completion_tokens_cap"] == 8192
    assert provider.calls == ["bear", "base", "bull"]
    assert result["candidate"]["action"] == "no_order"
    assert result["formal_eligibility"] is False
    assert result["provider_requests"] == 3
    assert all(row["status"] == "SETTLED" for row in result["reservations"].values())
    assert task.read(created["task_id"])["status"] == "SUCCEEDED"
    assert task.run(created["task_id"])["provider_requests"] == 3
    budget = task.daily.base / "budget" / NOW.astimezone(target.ZoneInfo("Asia/Shanghai")).date().isoformat()
    assert len(list((budget / "versions").glob("*.json"))) == 6


def test_ambiguous_call_never_resends_and_can_cancel(service):
    task, provider = service
    provider.fail_at = 2
    created = task.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
                          request_key="parentcash002", now=NOW)
    failed = task.run(created["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "PARENT_PROVIDER_TIMEOUT_AMBIGUOUS"
    assert failed["completed_scenarios"] == ["bear"]
    assert any(row["status"] == "RESERVED" for row in failed["reservations"].values())
    resumed = task.resume(created["task_id"], now=NOW)
    assert resumed["status"] == "FAILED"
    assert task.run(created["task_id"], now=NOW)["status"] == "FAILED"
    assert provider.calls == ["bear", "base"]
    assert task.cancel(created["task_id"], now=NOW)["status"] == "CANCELLED"


def test_request_key_conflict_and_checkpoint_tamper(service):
    task, provider = service
    binding = dict(path="runtime/spec.json", sha256="b" * 64)
    created = task.create(spec_binding=binding, request_key="parentcash003", now=NOW)
    with pytest.raises(ValueError, match="CONFLICT"):
        task.create(spec_binding=dict(path="runtime/other.json", sha256="b" * 64),
                    request_key="parentcash003", now=NOW)
    completed = task.run(created["task_id"], now=NOW)
    path = task.root / completed["responses"]["bear"]["path"]
    path.write_text("{}", encoding="utf-8")
    reopened = task.read(created["task_id"])
    assert reopened["status"] == "FAILED"
    assert reopened["error_code"] == "PARENT_SOURCE_OR_CHECKPOINT_INVALID"


def test_settled_charge_without_published_response_never_resends(service):
    task, provider = service
    created = task.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
                          request_key="parentcash004", now=NOW)
    completed = task.run(created["task_id"], now=NOW)
    spec, state, binding = task._load(created["task_id"])
    # Model a crash after settling a provider call but before publishing its
    # scenario response. The charge is irreversible; retry must not resend.
    responses = dict(state["responses"])
    responses.pop("bull")
    task._save(spec, state, binding, NOW, status="FAILED", responses=responses)
    assert task.resume(created["task_id"], now=NOW)["status"] == "FAILED"
    assert task.run(created["task_id"], now=NOW)["status"] == "FAILED"
    assert len(provider.calls) == 3
    assert completed["provider_requests"] == 3


def test_live_task_requires_existing_shared_budget_root(tmp_path, monkeypatch):
    monkeypatch.delenv("VALUE_AGENT_SHARED_RESEARCH_ROOT", raising=False)
    task = target.ParentCashTaskService(tmp_path)
    with pytest.raises(PermissionError, match="SHARED_BUDGET_ROOT_REQUIRED"):
        task.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
                    request_key="parentcash005", now=NOW)


def test_shared_budget_head_tamper_invalidates_completed_result(service):
    task, _ = service
    created = task.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
                          request_key="parentcash006", now=NOW)
    completed = task.run(created["task_id"], now=NOW)
    assert completed["status"] == "SUCCEEDED"
    day = next(iter(completed["reservations"].values()))["day"]
    head = task.daily.base / "budget" / day / "current.json"
    head.write_text("{}", encoding="utf-8")
    reread = task.read(created["task_id"])
    assert reread["status"] == "FAILED"
    assert reread["error_code"] == "PARENT_SOURCE_OR_CHECKPOINT_INVALID"
