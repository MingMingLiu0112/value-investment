"""TEST_ONLY durable split runner; real public originals, no network."""
from types import SimpleNamespace
from decimal import Decimal
import json

from test_operating_horizon_task_v5_wc import env, NOW, wps_hardlink_fallback
from test_operating_horizon_draft_v3 import payload
from value_investment_agent.application.research.agent_review import operating_horizon_task_v6_split as mod
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


def service(env, monkeypatch, *, fail_cash=False):
    complete = payload()
    annual = json.loads(json.dumps(complete))
    cash = annual["years"]["2026"].pop("shareholder_cash_paths")
    calls = []

    def respond(request):
        stage = "cash" if "annual_response_sha256" in request.output_schema["properties"] else "annual"
        calls.append(stage)
        if stage == "cash" and fail_cash:
            raise TimeoutError("TEST_ONLY timeout")
        if stage == "annual":
            text = json.dumps(annual)
        else:
            bound = json.loads(request.user)["annual_response_sha256"]
            text = json.dumps({"year": "2026", "annual_response_sha256": bound,
                               "shareholder_cash_paths": cash})
        return LLMResponse(text, 100, 50, "TEST_ONLY")

    monkeypatch.setattr(mod, "_now", lambda value=None: value or NOW)
    prior = env.service()
    runner = mod.OperatingHorizonTaskService(env.root,
        test_provider=SimpleNamespace(complete=respond),
        source_loader=prior.source_loader,
        source_loader_version="test-only-source-v1")
    return runner, calls


def test_two_stage_persistence_and_replay(env, monkeypatch):
    runner, calls = service(env, monkeypatch)
    task = runner.create(symbol="600519", request_key="V6_TWO_STAGE_TEST", years=[2026], now=NOW)
    assert task["annual_status"] == "PENDING" and task["cash_status"] == "PENDING"
    result = runner.run(task["task_id"], now=NOW)
    assert result["status"] == "SUCCEEDED", result
    assert calls == ["annual", "cash"]
    assert result["annual_status"] == result["cash_status"] == "SETTLED_VALIDATED"
    assert result["research_result"]["cash_policy_appendix_status"] == "COMPLETE_UNAPPROVED"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["new_llm_calls"] == 0 and result["provider_requests"] == 2
    assert len(result["reservations"]) == 2
    assert all(row["status"] == "SETTLED" for row in result["reservations"].values())
    assert Decimal(result["reserved_cost"]) == 0
    again = runner.read(task["task_id"])
    assert again["research_result"] == result["research_result"]
    assert runner.run(task["task_id"], now=NOW)["status"] == "SUCCEEDED"
    assert calls == ["annual", "cash"]


def test_failed_cash_intent_never_repeats_provider_call(env, monkeypatch):
    runner, calls = service(env, monkeypatch, fail_cash=True)
    task = runner.create(symbol="600519", request_key="V6_AMBIGUOUS_CASH", years=[2026], now=NOW)
    failed = runner.run(task["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["annual_status"] == "SETTLED_VALIDATED"
    assert failed["cash_status"] == "AMBIGUOUS_CALL_NO_RETRY"
    assert failed["research_result"] is None and calls == ["annual", "cash"]
    runner.resume(task["task_id"], now=NOW)
    runner.run(task["task_id"], now=NOW)
    assert calls == ["annual", "cash"]


def test_cancelled_task_never_calls_provider(env, monkeypatch):
    runner, calls = service(env, monkeypatch)
    task = runner.create(symbol="600519", request_key="V6_CANCEL_BEFORE_RUN", years=[2026], now=NOW)
    cancelled = runner.cancel(task["task_id"], now=NOW)
    assert cancelled["status"] == "CANCELLED"
    assert runner.run(task["task_id"], now=NOW)["status"] == "CANCELLED"
    assert calls == []


def test_cancel_during_annual_call_never_starts_cash(env, monkeypatch):
    runner, calls = service(env, monkeypatch)
    task = runner.create(symbol="600519", request_key="V6_CANCEL_AFTER_ANNUAL", years=[2026], now=NOW)
    original = runner.test_provider.complete
    def cancel_after_return(request):
        response = original(request)
        runner.cancel(task["task_id"], now=NOW)
        return response
    runner.test_provider.complete = cancel_after_return
    cancelled = runner.run(task["task_id"], now=NOW)
    assert cancelled["status"] == "CANCELLED" and cancelled["research_result"] is None
    assert calls == ["annual"]
    assert cancelled["cash_status"] == "PENDING"


def test_resume_after_annual_checkpoint_calls_only_cash(env, monkeypatch):
    runner, calls = service(env, monkeypatch)
    task = runner.create(symbol="600519", request_key="V6_ANNUAL_CHECKPOINT", years=[2026], now=NOW)
    original = runner._request_for_stage
    def interrupt(spec, state, context, stage):
        if stage == "cash":
            raise ValueError("V6_SPLIT_TEST_ONLY_STAGE_INTERRUPT")
        return original(spec, state, context, stage)
    monkeypatch.setattr(runner, "_request_for_stage", interrupt)
    failed = runner.run(task["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["annual_status"] == "SETTLED_VALIDATED"
    assert failed["cash_status"] == "PENDING" and calls == ["annual"]
    monkeypatch.setattr(runner, "_request_for_stage", original)
    assert runner.resume(task["task_id"], now=NOW)["status"] == "QUEUED"
    completed = runner.run(task["task_id"], now=NOW)
    assert completed["status"] == "SUCCEEDED" and calls == ["annual", "cash"]


def test_changed_annual_checkpoint_blocks_cash_stage(env, monkeypatch):
    runner, calls = service(env, monkeypatch)
    task = runner.create(symbol="600519", request_key="V6_CHANGED_ANNUAL", years=[2026], now=NOW)
    original = runner._request_for_stage
    def interrupt(spec, state, context, stage):
        if stage == "cash":
            raise ValueError("V6_SPLIT_TEST_ONLY_STAGE_INTERRUPT")
        return original(spec, state, context, stage)
    monkeypatch.setattr(runner, "_request_for_stage", interrupt)
    assert runner.run(task["task_id"], now=NOW)["annual_status"] == "SETTLED_VALIDATED"
    response = runner._directory(task["task_id"]) / "response-annual.json"
    response.write_bytes(response.read_bytes() + b" ")
    assert runner.read(task["task_id"])["error_code"] == "V6_SPLIT_REPLAY_INVALID"
    runner.resume(task["task_id"], now=NOW)
    monkeypatch.setattr(runner, "_request_for_stage", original)
    assert runner.run(task["task_id"], now=NOW)["status"] == "FAILED"
    assert calls == ["annual"]
