"""TEST_ONLY nine-stage D1 task on existing immutable store and shared ledger."""
import json
import sys
import types
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from value_investment_agent.application.research.agent_review import parent_cash_task_v3 as target
from value_investment_agent.application.research import direct_owner_cash_staged_v2 as staged
from value_investment_agent.application.research import direct_owner_cash_staged_v3 as staged_numbered
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
            policy = {key: term(1) for key in fields}
            # Stable terminal cash covers recurring outflows and excludes finite commitments.
            policy["commitments_outside_capex"]["values"] = ["0"]
            policy["operating_cash"]["values"] = ["3.75"]
            body = dict(terminal=dict(policy=policy,
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
        if "scenario_review" in request.output_schema["required"]:
            body["scenario_review"] = [body.pop(key) for key in target.operating_wire.REVIEW_FIELDS]
        return LLMResponse(json.dumps(body), 100, 100, "deepseek-flash")


@pytest.fixture
def task(tmp_path, monkeypatch):
    def fact(field, value, section="operating"):
        return dict(field=field, value_cny=value, section=section,
            period_end="2025-12-31", column="current",
            scope="ISSUER_PARENT_STANDALONE", source_refs=[{"sha256": "a" * 64}])
    context = dict(input_fingerprint="a" * 64, symbol="600887",
        valuation_date="2025-12-31", opening_fact_anchors={"cash": "cash"},
        facts={"profit": fact("parent_net_profit_cny", "10", "income"),
            "revenue": fact("revenue", "10"), "cost": fact("cost", "10"),
            "receipts": fact("customer_cash", "10"),
            "paid": fact("supplier_cash", "10"),
            "cfo": fact("cfo", "10"),
            "cash": fact("closing_cash_and_equivalents_cny", "100", "balance_sheet"),
            "debt": fact("liabilities_cny", "0", "balance_sheet")})
    module_name = "value_investment_agent.application.research.direct_owner_cash_agent_facts_v2"
    facts_stub = types.ModuleType(module_name)
    facts_stub.__file__ = str(Path(target.__file__).parent.parent / "direct_owner_cash_agent_facts_v1.py")
    monkeypatch.setitem(sys.modules, module_name, facts_stub)
    monkeypatch.setattr(target, "model_configuration", lambda root: CFG.copy())
    monkeypatch.setattr(target, "read_parent_cash_agent_facts_v2", lambda **_: context)
    monkeypatch.setattr(staged, "read_parent_cash_agent_facts", lambda **_: context)
    monkeypatch.setattr(staged, "_load_spec", lambda root, binding:
                        {"operating_sources": [{"path": "fixture", "sha256": "a" * 64}],
                         "opening": {"cash": {"classification": "FACT", "anchor": "cash"}}})
    monkeypatch.setattr(staged_numbered, "_load_spec", lambda root, binding:
                        {"opening": {"debt": {"classification": "FACT", "anchor": "debt"}}})
    monkeypatch.setattr(staged, "read_parent_direct_cash_research", lambda **_:
                        {"observed": [dict(symbol="600887", scope="ISSUER_PARENT_STANDALONE",
                            currency="CNY", classification="FACT",
                            period_start="2025-01-01", period_end="2025-12-31",
                            revenue="10", cost="10", customer_cash="10", supplier_cash="10",
                            cfo="10", source_refs=[{"sha256": "a" * 64}])]})
    monkeypatch.setattr(target, "assemble_parent_cash_drafts_v2", lambda **_:
        dict(action="no_order", formal_eligibility=False, main_range_adopted=False))
    monkeypatch.setattr(target, "preflight_annual_cash_upper_bound_v3", lambda **_: None)
    provider = Provider()
    return target.ParentCashTaskServiceV3(tmp_path, test_provider=provider), provider


def test_nine_stages_and_shared_budget(task):
    service, provider = task
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashv3001", now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "SUCCEEDED", result.get("error_code")
    assert result["completed_scenarios"] == ["base", "bear", "bull"]
    assert result["completed_stages"] == list(target.STAGE_ORDER)
    assert len(provider.calls) == 9 and result["provider_requests"] == 9
    assert result["candidate"]["action"] == "no_order"
    assert result["formal_eligibility"] is False
    assert service.read(created["task_id"])["status"] == "SUCCEEDED"
    assert len(provider.calls) == 9


def test_old_implementation_retains_original_failure_without_replay(task, monkeypatch):
    service, provider = task
    provider.fail_at = 1
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashv3history", now=NOW)
    failed = service.run(created["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    original_error = failed["error_code"]
    monkeypatch.setattr(target, "_implementation", lambda: "0" * 64)
    historical = service.read(created["task_id"])
    assert historical["historical_status"] == "FAILED"
    assert historical["historical_error_code"] == original_error
    assert historical["error_code"] == "PARENT_IMPLEMENTATION_CHANGED_REPLAY_REQUIRED"
    assert "candidate" not in historical


def test_ambiguous_stage_never_resends(task):
    service, provider = task
    provider.fail_at = 2
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashv3002", now=NOW)
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
        request_key="parentcashv3003", now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "BEAR_OPERATING_PARENT_V3_YEARS_OR_SERIES_INVALID"
    assert result["completed_stages"] == []
    assert result["settled_cost"] != "0"
    assert service.resume(created["task_id"], now=NOW)["status"] == "FAILED"


def test_economic_rejection_keeps_all_raw_responses(task, monkeypatch):
    service, provider = task
    monkeypatch.setattr(target, "assemble_parent_cash_drafts_v2", lambda **_:
                        (_ for _ in ()).throw(ValueError("DIRECT_OWNER_UNCONSUMED_FUTURE_EVENTS")))
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashv3004", now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "PARENT_V3_ECONOMIC_DIRECT_OWNER_UNCONSUMED_FUTURE_EVENTS"
    assert len(provider.calls) == 9
    assert len(result["returned_responses"]) == 9
    assert "candidate" not in result


def test_economic_cash_rejection_preserves_the_year(task, monkeypatch):
    service, _ = task
    monkeypatch.setattr(target, "assemble_parent_cash_drafts_v2", lambda **_:
                        (_ for _ in ()).throw(ValueError(
                            "DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2026")))
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashyear001", now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == (
        "PARENT_V3_ECONOMIC_DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2026")
    assert "candidate" not in result


def test_unfunded_policy_stops_before_terminal_call(task, monkeypatch):
    service, provider = task
    monkeypatch.setattr(staged_numbered, "_load_spec", lambda *_args: {
        "symbol": "600887", "valuation_date": "2025-12-31",
        "opening": {"cash": {"classification": "FACT", "anchor": "cash"}}})
    monkeypatch.setattr(staged_numbered, "_historical_parent_operating_cash",
        lambda **_kwargs: dict(symbol="600887", scope="ISSUER_PARENT_STANDALONE",
            currency="CNY", classification="FACT", period_start="2025-01-01",
            period_end="2025-12-31", revenue="10", cost="10",
            customer_cash="10", supplier_cash="10", cfo="10",
            source_refs=[{"sha256": "a" * 64}]))
    monkeypatch.setattr(target, "preflight_annual_cash_upper_bound_v3",
                        staged_numbered.preflight_annual_cash_upper_bound_v3)
    class UnfundedProvider(Provider):
        def complete(self, request):
            response = super().complete(request)
            if json.loads(request.user)["stage"] != "policy":
                return response
            body = json.loads(response.text)
            body["series"]["debt_repayment"]["values"][0] = "200"
            return LLMResponse(json.dumps(body), 100, 100, "deepseek-flash")
    service.test_provider = UnfundedProvider()
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashpreflight001", now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == (
        "BEAR_POLICY_PARENT_V3_ECONOMIC_DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2026")
    assert result["completed_stages"] == ["bear.operating", "bear.policy"]
    assert len(result["returned_responses"]) == 2
    assert service.test_provider.calls == [("bear", "operating"), ("bear", "policy")]
    assert "candidate" not in result
    fork = service.create(spec_binding=created["spec_binding"],
        request_key="parentcashpreflightfork001", now=NOW,
        seed_task_id=created["task_id"])
    fork_result = service.run(fork["task_id"], now=NOW)
    assert fork_result["status"] == "FAILED"
    assert fork_result["error_code"] == result["error_code"]
    assert service.test_provider.calls == [("bear", "operating"), ("bear", "policy")]


def test_budget_head_tamper_invalidates_completed_view(task):
    service, _ = task
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashv3005", now=NOW)
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
    monkeypatch.setattr(target, "read_parent_cash_agent_facts_v2", lambda **_: context)
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
            status="FAILED", error_code="BEAR_POLICY_PARENT_V3_OLD_PARSER_REJECTED")
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


def test_replay_from_later_stage_reuses_unchanged_prefix(task, monkeypatch):
    service, provider = task
    monkeypatch.setattr(target, "assemble_parent_cash_drafts_v2", lambda **_:
                        (_ for _ in ()).throw(ValueError("DIRECT_OWNER_UNCONSUMED_FUTURE_EVENTS")))
    original = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashfork011", now=NOW)
    assert service.run(original["task_id"], now=NOW)["status"] == "FAILED"
    monkeypatch.setattr(target, "assemble_parent_cash_drafts_v2", lambda **_:
        dict(action="no_order", formal_eligibility=False, main_range_adopted=False))
    fork = service.create(spec_binding=original["spec_binding"],
        request_key="parentcashfork012", now=NOW, seed_task_id=original["task_id"],
        replay_from_stage="bull.policy")
    assert fork["completed_stages"] == list(target.STAGE_ORDER[:7])
    assert service.run(fork["task_id"], now=NOW)["status"] == "SUCCEEDED"
    assert len(provider.calls) == 11 and service.read(original["task_id"])["status"] == "FAILED"


def test_terminal_replay_keeps_independent_scenarios(task, monkeypatch):
    service, provider = task
    monkeypatch.setattr(target, "assemble_parent_cash_drafts_v2", lambda **_:
                        (_ for _ in ()).throw(ValueError("DIRECT_OWNER_TERMINAL_DEBT_POLICY_UNSUPPORTED")))
    original = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashfork013", now=NOW)
    assert service.run(original["task_id"], now=NOW)["status"] == "FAILED"
    monkeypatch.setattr(target, "assemble_parent_cash_drafts_v2", lambda **_:
        dict(action="no_order", formal_eligibility=False, main_range_adopted=False))
    fork = service.create(spec_binding=original["spec_binding"],
        request_key="parentcashfork014", now=NOW, seed_task_id=original["task_id"],
        replay_from_stage="bear.terminal")
    assert fork["completed_stages"] == [item for item in target.STAGE_ORDER
                                         if item != "bear.terminal"]
    assert service.run(fork["task_id"], now=NOW)["status"] == "SUCCEEDED"
    assert fork["provider_requests"] == 0 and len(provider.calls) == 10


def test_fork_run_cost_counts_ancestor_reservations(task, monkeypatch):
    service, provider = task
    monkeypatch.setitem(CFG, "input_cost_per_million", "100")
    monkeypatch.setitem(CFG, "output_cost_per_million", "100")
    monkeypatch.setitem(CFG, "max_run_cost", "3")
    monkeypatch.setitem(CFG, "daily_cost_limit", "10")
    provider.fail_at = 2
    original = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashfork015", now=NOW)
    failed = service.run(original["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    fork = service.create(spec_binding=original["spec_binding"],
        request_key="parentcashfork016", now=NOW, seed_task_id=original["task_id"])
    assert float(fork["provider_requests"]) == 0
    assert Decimal(service._load(fork["task_id"])[0]["ancestor_spend"]) > 0
    provider.fail_at = None
    result = service.run(fork["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "PARENT_TASK_BUDGET_EXHAUSTED"
    assert result["provider_requests"] == 0 and len(provider.calls) == 2


def test_existing_fork_key_returns_failed_provenance_view(task):
    service, provider = task
    provider.fail_at = 3
    original = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashfork017", now=NOW)
    service.run(original["task_id"], now=NOW)
    fork = service.create(spec_binding=original["spec_binding"],
        request_key="parentcashfork018", now=NOW, seed_task_id=original["task_id"])
    service.cancel(original["task_id"], now=NOW)
    repeated = service.create(spec_binding=original["spec_binding"],
        request_key="parentcashfork018", now=NOW, seed_task_id=original["task_id"])
    assert repeated["task_id"] == fork["task_id"]
    assert repeated["status"] == "FAILED"
    assert repeated["error_code"] == "PARENT_SOURCE_OR_CHECKPOINT_INVALID"


def test_v3_namespace_does_not_open_v2_task(task, monkeypatch):
    from value_investment_agent.application.research.agent_review import parent_cash_task_v2 as old
    service, _ = task
    monkeypatch.setattr(old, "model_configuration", lambda root: CFG.copy())
    monkeypatch.setattr(old, "read_parent_cash_agent_facts",
                        lambda **_: target.read_parent_cash_agent_facts_v2())
    legacy = old.ParentCashTaskServiceV2(service.root, test_provider=Provider())
    binding = dict(path="runtime/spec.json", sha256="b" * 64)
    old_task = legacy.create(spec_binding=binding, request_key="same-key", now=NOW)
    new_task = service.create(spec_binding=binding, request_key="same-key", now=NOW)
    assert old_task["task_id"] != new_task["task_id"]
    assert legacy.read(old_task["task_id"])["mode"] == "TEST_ONLY_PARENT_CASH_V2"
    assert service.read(new_task["task_id"])["mode"] == "TEST_ONLY_PARENT_CASH_V3"
    with pytest.raises(FileNotFoundError):
        service.read(old_task["task_id"])
    with pytest.raises(FileNotFoundError):
        legacy.read(new_task["task_id"])
    assert legacy.read(old_task["task_id"])["status"] == "QUEUED"


def test_operating_wire_rejects_duplicate_keys_after_sealing(task):
    service, _ = task

    class DuplicateReviewProvider(Provider):
        def complete(self, request):
            response = super().complete(request)
            return LLMResponse(response.text[:-1] + ', "scenario_review": []}',
                               100, 100, "deepseek-flash")

    service.test_provider = DuplicateReviewProvider()
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
                             request_key="duplicate-wire-stage", now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["error_code"] == "BEAR_OPERATING_PARENT_V3_CONFLICTING_JSON_KEY"
    assert result["completed_stages"] == []
    assert len(service._load(created["task_id"])[1]["returned_responses"]) == 1


def test_policy_wire_error_preserves_year_and_allowed_field(task, monkeypatch):
    service, _ = task

    def reject(**_kwargs):
        raise ValueError("PARENT_V3_POLICY_CNY_WIRE_INVALID:2027:growth_capex")

    monkeypatch.setattr(target, "preflight_annual_cash_upper_bound_v3", reject)
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
                             request_key="parentcash-wire-reason", now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "BEAR_POLICY_PARENT_V3_POLICY_CNY_WIRE_INVALID:2027:growth_capex"
