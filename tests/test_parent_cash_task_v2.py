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


def test_failed_task_fork_reuses_verified_prefix_without_recharge(task):
    service, provider = task
    provider.fail_at = 3
    original = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashfork001", now=NOW)
    failed = service.run(original["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["completed_stages"] == ["bear.operating", "bear.policy"]
    provider.fail_at = None
    fork = service.create(spec_binding=original["spec_binding"],
        request_key="parentcashfork002", now=NOW, seed_task_id=original["task_id"])
    assert fork["completed_stages"] == ["bear.operating", "bear.policy"]
    result = service.run(fork["task_id"], now=NOW)
    assert result["status"] == "SUCCEEDED", result.get("error_code")
    assert result["provider_requests"] == 7
    assert len(provider.calls) == 10  # 3 original attempts plus 7 new calls
    assert service.read(original["task_id"])["status"] == "FAILED"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False


def test_fork_rejects_changed_source_and_old_checkpoint(task, monkeypatch):
    service, provider = task
    provider.fail_at = 3
    original = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashfork003", now=NOW)
    service.run(original["task_id"], now=NOW)
    fork = service.create(spec_binding=original["spec_binding"],
        request_key="parentcashfork004", now=NOW, seed_task_id=original["task_id"])
    service.cancel(original["task_id"], now=NOW)
    assert service.read(fork["task_id"])["error_code"] == "PARENT_SOURCE_OR_CHECKPOINT_INVALID"
    context = dict(input_fingerprint="c" * 64, symbol="600887",
        valuation_date="2025-12-31", facts={"profit": {"period_end": "2025-12-31"}})
    monkeypatch.setattr(target, "read_parent_cash_agent_facts", lambda **_: context)
    with pytest.raises(ValueError, match="PARENT_SEED_INCOMPATIBLE"):
        service.create(spec_binding=original["spec_binding"],
            request_key="parentcashfork005", now=NOW, seed_task_id=original["task_id"])


def test_fork_recovers_settled_raw_response_rejected_by_old_parser(task):
    service, provider = task
    provider.fail_at = 3
    original = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashfork006", now=NOW)
    service.run(original["task_id"], now=NOW)
    with service._lock(service._directory(original["task_id"])):
        spec, state, head = service._load(original["task_id"])
        # Stand in for a response sealed and settled before an older parser rejected it.
        policy_binding = state["responses"]["bear.policy"]
        responses = dict(state["responses"])
        del responses["bear.policy"]
        service._save(spec, state, head, NOW, responses=responses,
            status="FAILED", error_code="BEAR_POLICY_PARENT_V2_OLD_PARSER_REJECTED")
    fork = service.create(spec_binding=original["spec_binding"],
        request_key="parentcashfork007", now=NOW, seed_task_id=original["task_id"])
    assert fork["completed_stages"] == ["bear.operating", "bear.policy"]
    fork_spec, fork_state, _ = service._load(fork["task_id"])
    assert fork_state["responses"]["bear.policy"] == policy_binding
    assert fork_spec["seed"]["task_id"] == original["task_id"]
    assert fork["provider_requests"] == 0
    assert len(provider.calls) == 3
    assert service.create(spec_binding=original["spec_binding"],
        request_key="parentcashfork007", now=NOW, seed_task_id=original["task_id"])["task_id"] == fork["task_id"]


def test_nested_fork_revalidates_original_provenance_chain(task):
    service, provider = task
    provider.fail_at = 3
    original = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashfork008", now=NOW)
    service.run(original["task_id"], now=NOW)
    first = service.create(spec_binding=original["spec_binding"],
        request_key="parentcashfork009", now=NOW, seed_task_id=original["task_id"])
    provider.fail_at = 4
    assert service.run(first["task_id"], now=NOW)["status"] == "FAILED"
    second = service.create(spec_binding=original["spec_binding"],
        request_key="parentcashfork010", now=NOW, seed_task_id=first["task_id"])
    assert second["completed_stages"] == ["bear.operating", "bear.policy"]
    service.cancel(original["task_id"], now=NOW)
    assert service.read(second["task_id"])["error_code"] == "PARENT_SOURCE_OR_CHECKPOINT_INVALID"
