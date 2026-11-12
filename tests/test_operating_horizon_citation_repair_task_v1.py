"""TEST_ONLY one-call repair lifecycle; never uses a paid provider."""
from datetime import timedelta
import json
from uuid import uuid4

import pytest

from test_operating_horizon_citation_repair_v1 import SealedTask, proposal
from test_operating_horizon_draft_v1 import NOW, context
from value_investment_agent.application.research.agent_review import operating_horizon_citation_repair_task_v1 as task_module
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


class Provider:
    calls = 0

    def __init__(self, response):
        self.response = response

    def complete(self, request):
        self.calls += 1
        return self.response


@pytest.fixture
def service(tmp_path_factory, context, monkeypatch):
    root = tmp_path_factory.getbasetemp() / ("r" + uuid4().hex[:6])
    original = SealedTask(context)
    config = dict(model_id="TEST_ONLY", max_completion_tokens_cap=1024,
                  max_run_cost="1", daily_cost_limit="10", currency="CNY",
                  input_cost_per_million="1", output_cost_per_million="1")
    original.spec["config"] = config
    monkeypatch.setattr(task_module.live, "model_configuration", lambda root: config)
    provider = Provider(LLMResponse(text=proposal(original), model_id="TEST_ONLY",
                                    prompt_tokens=100, completion_tokens=100, tool_calls=0))
    service = task_module.CitationRepairTaskService(root, test_provider=provider)
    service.original = original
    monkeypatch.setattr(service, "_provider", lambda spec: provider)
    return service, original, provider


def test_one_call_idempotent_and_unapproved_replay(service):
    runner, original, provider = service
    before = (json.dumps(original.spec), json.dumps(original.state), json.dumps(original.packet))
    created = runner.create(original_task_id="rt-sealed-test", request_key="request-key-1", now=NOW)
    repeated = runner.create(original_task_id="rt-sealed-test", request_key="request-key-1",
                             now=NOW + timedelta(seconds=1))
    assert created["task_id"] == repeated["task_id"]
    result = runner.run(created["task_id"], now=NOW + timedelta(minutes=1))
    assert result["status"] == "SUCCEEDED" and result["research_admission"] is False
    assert result["e2_promotion"] is False and result["formal_eligibility"] is False
    assert result["repair_result"]["requires_semantic_evidence_review"] is True
    assert runner.read(created["task_id"])["status"] == "SUCCEEDED"
    assert runner.resume(created["task_id"])["status"] == "SUCCEEDED"
    assert runner.run(created["task_id"])["status"] == "SUCCEEDED"
    assert provider.calls == 1
    assert before == (json.dumps(original.spec), json.dumps(original.state), json.dumps(original.packet))


def test_bad_replacement_is_sealed_but_not_accepted(service):
    runner, original, provider = service
    provider.response = LLMResponse(text=proposal(original, "forged:id"), model_id="TEST_ONLY",
                                    prompt_tokens=100, completion_tokens=100, tool_calls=0)
    created = runner.create(original_task_id="rt-sealed-test", request_key="request-key-2", now=NOW)
    result = runner.run(created["task_id"])
    assert result["status"] == "FAILED" and result["e2_promotion"] is False
    assert result["response_binding"] is not None
    assert runner.resume(created["task_id"])["status"] == "FAILED"
    assert provider.calls == 1


def test_ambiguous_intent_never_repeats_provider(service):
    runner, _, provider = service
    created = runner.create(original_task_id="rt-sealed-test", request_key="request-key-3", now=NOW)
    directory = runner._directory(created["task_id"])
    with runner._lock(directory):
        spec, state, pin = runner._load(created["task_id"])
        runner._save(spec, state, pin, NOW, status="RUNNING", provider_requests=1)
    assert runner.resume(created["task_id"])["error_code"] == "REPAIR_AMBIGUOUS_CALL_NO_REPEAT"
    runner.run(created["task_id"])
    assert provider.calls == 0


def test_cancel_and_changed_source_fail_closed(service):
    runner, original, provider = service
    created = runner.create(original_task_id="rt-sealed-test", request_key="request-key-4", now=NOW)
    assert runner.cancel(created["task_id"])["status"] == "CANCELLED"
    runner.run(created["task_id"])
    assert provider.calls == 0
    original.ctx["evidence"][0]["text"] = "tampered"
    assert runner.read(created["task_id"])["status"] == "CANCELLED"
    with pytest.raises(ValueError, match="SOURCE_HASH_CHANGED"):
        runner.create(original_task_id="rt-sealed-test", request_key="request-key-5", now=NOW)


def test_daily_budget_blocks_before_provider_and_preserves_task(service, monkeypatch):
    runner, _, provider = service
    created = runner.create(original_task_id="rt-sealed-test", request_key="request-key-6", now=NOW)
    monkeypatch.setattr(runner, "_daily_budget", lambda *args, **kwargs: (_ for _ in ()).throw(
        ValueError("DAILY_BUDGET_EXHAUSTED_BEFORE_CALL")))
    with pytest.raises(ValueError, match="DAILY_BUDGET_EXHAUSTED_BEFORE_CALL"):
        runner.run(created["task_id"])
    assert runner.read(created["task_id"])["provider_requests"] == 0
    assert provider.calls == 0


def test_provider_failure_keeps_reservation_and_never_repeats(service, monkeypatch):
    runner, _, provider = service
    created = runner.create(original_task_id="rt-sealed-test", request_key="request-key-7", now=NOW)
    def fail(request):
        provider.calls += 1
        raise TimeoutError("provider timeout")
    monkeypatch.setattr(provider, "complete", fail)
    result = runner.run(created["task_id"])
    assert result["status"] == "FAILED"
    assert result["error_code"] == "REPAIR_CALL_OR_SETTLEMENT_AMBIGUOUS_NO_REPEAT"
    assert result["provider_requests"] == 1
    assert next(iter(result["reservations"].values()))["status"] == "RESERVED"
    runner.resume(created["task_id"])
    runner.run(created["task_id"])
    assert provider.calls == 1
