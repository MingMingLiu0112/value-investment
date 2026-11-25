"""TEST_ONLY nine-stage D1 task on existing immutable store and shared ledger."""
import json
import sys
import types
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
from urllib.error import HTTPError, URLError

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


@pytest.mark.parametrize(("amounts", "error"), [
    (["100", "20", "1"], "COUPON_COVERAGE_LOW:2026"),
    (["125", "0", "1"], "COUPON_COVERAGE_LOW:2027"),
    (["125", "20", "0"], "DEBT_INTEREST_UNSUPPORTED:2028"),
    (["125", "20", "1"], None),
])
def test_scenario_interest_covers_paid_and_conditional_coupons(amounts, error):
    debt = [dict(year=year, opening_debt_cny="50", new_borrowing_cny="0")
            for year in (2026, 2027, 2028)]
    source = {"annual_paid_note_interest_floor": {"year": 2026, "minimum_cny": "100"}}
    calendar = {"issues": [
        {"maturity": "2026-12-30", "conditional_act365_cash_cny": "25"},
        {"maturity": "2027-11-12", "conditional_act365_cash_cny": "20"},
    ]}
    policy = {"series": {"interest_outside_cfo": {"values": amounts}}}
    if error is None:
        target._validate_scenario_interest(policy, debt, source, calendar)
    else:
        with pytest.raises(ValueError, match=error):
            target._validate_scenario_interest(policy, debt, source, calendar)


class Provider:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def complete(self, request):
        packet = json.loads(request.user)
        self.calls.append((packet["scenario"], packet["stage"]))
        if len(self.calls) == self.fail_at:
            raise getattr(self, "failure", TimeoutError("ambiguous transport"))
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


@pytest.mark.parametrize(("error", "code"), [
    (TimeoutError("transport"), "TIMEOUT_AMBIGUOUS"),
    (HTTPError("https://example.invalid", 429, "private provider detail", {}, None), "HTTP_429_UNSETTLED"),
    (URLError(TimeoutError("transport")), "TIMEOUT_AMBIGUOUS"),
    (URLError("private provider detail"), "CONNECTION_AMBIGUOUS"),
])
def test_ambiguous_stage_never_resends(task, error, code):
    service, provider = task
    provider.fail_at = 2
    provider.failure = error
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashv3002", now=NOW)
    failed = service.run(created["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == f"BEAR_POLICY_PARENT_PROVIDER_{code}"
    assert Decimal(failed["reserved_cost"]) > 0
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
        "opening": {"cash": {"classification": "FACT", "anchor": "cash"},
                    "debt": {"classification": "FORECAST_ASSUMPTION", "value": "1000"}}})
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


def test_policy_fork_retains_source_anchored_base_operating(task, monkeypatch):
    service, provider = task
    reader = target.read_parent_cash_agent_facts_v2
    monkeypatch.setattr(target, "read_parent_cash_agent_facts_v2", lambda **kwargs:
        dict(reader(**kwargs), parent_operating_cash_observations=[
            dict(symbol="600887", scope="ISSUER_PARENT_STANDALONE",
                 period_end="2025-12-31", cfo="3", customer_cash="10",
                 supplier_cash="5", revenue="10", cost="10", source_refs=[{"sha256": "a" * 64}]),
        ]))
    binding = dict(path="runtime/spec.json", sha256="b" * 64)
    original = service.create(spec_binding=binding, request_key="base-original", now=NOW)
    provider.fail_at = 4
    assert service.run(original["task_id"], now=NOW)["status"] == "FAILED"

    operating = service.create(spec_binding=binding, request_key="base-operating",
        seed_task_id=original["task_id"], replay_from_stage="base.operating", now=NOW)
    provider.fail_at = 6
    failure = service.run(operating["task_id"], now=NOW)
    assert failure["error_code"] == "BASE_POLICY_PARENT_PROVIDER_TIMEOUT_AMBIGUOUS"
    assert failure["completed_stages"] == list(target.STAGE_ORDER[:4])

    policy = service.create(spec_binding=binding, request_key="base-policy",
        seed_task_id=operating["task_id"], replay_from_stage="base.policy", now=NOW)
    assert policy["completed_stages"] == failure["completed_stages"]
    assert len(provider.calls) == 6
    assert service._load(policy["task_id"])[0]["seed"]["responses"]["base.operating"] == (
        service._load(operating["task_id"])[1]["responses"]["base.operating"])


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


def test_policy_wire_preserves_strict_term_rejection(task):
    service, _ = task

    class ExtraPolicyFieldProvider(Provider):
        def complete(self, request):
            response = super().complete(request)
            if json.loads(request.user)["stage"] != "policy":
                return response
            payload = json.loads(response.text)
            payload["series"]["cash_floor"]["counter_evidence_na"] = None
            return LLMResponse(json.dumps(payload), 100, 100, "deepseek-flash")

    service.test_provider = ExtraPolicyFieldProvider()
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
                             request_key="extra-policy-term-field", now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "BEAR_POLICY_PARENT_DRAFT_TERM_SOURCE_INVALID"
    assert result["completed_stages"] == ["bear.operating"]
    assert service.read(created["task_id"])["error_code"] == result["error_code"]


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


def test_negative_debt_before_terminal_request_persists_failure(task, monkeypatch):
    service, provider = task
    build = target.staged_parent_cash_request_v3

    def reject_terminal(**kwargs):
        if kwargs["stage"] == "terminal":
            raise ValueError("PARENT_V3_FORECAST_DEBT_NEGATIVE")
        return build(**kwargs)

    monkeypatch.setattr(target, "staged_parent_cash_request_v3", reject_terminal)
    created = service.create(spec_binding=dict(path="runtime/spec.json", sha256="b" * 64),
        request_key="parentcashdebtguard", now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "BEAR_TERMINAL_PARENT_V3_FORECAST_DEBT_NEGATIVE"
    assert result["completed_stages"] == ["bear.operating", "bear.policy"]
    assert len(provider.calls) == 2
    assert service.read(created["task_id"])["error_code"] == result["error_code"]

def test_policy_debt_failure_is_sealed_without_terminal_request(task):
    service, _ = task
    class NegativeDebtProvider(Provider):
        def complete(self, request):
            response = super().complete(request)
            if json.loads(request.user)["stage"] != "policy":
                return response
            assert json.loads(request.user)["opening_debt_basis"]["amount_cny"] == "0"
            body = json.loads(response.text)
            body["series"]["debt_repayment"]["values"][0] = "2.25"
            return LLMResponse(json.dumps(body), 100, 100, "deepseek-flash")
    provider = NegativeDebtProvider()
    service.test_provider = provider
    created = service.create(spec_binding=dict(path="runtime/spec.json",sha256="b"*64),
        request_key="policynegative001",now=NOW)
    result = service.run(created["task_id"],now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "BEAR_POLICY_PARENT_V3_FORECAST_DEBT_NEGATIVE"
    assert provider.calls == [("bear","operating"),("bear","policy")]
    assert len(result["returned_responses"]) == 2
    assert service.read(created["task_id"])["error_code"] == result["error_code"]


@pytest.mark.parametrize("unit,expect_error", [("元", False), ("万元", True)])
def test_terminal_cost_method_income_requires_parent_note_and_cny_columns(unit, expect_error):
    from value_investment_agent.application.research import parent_direct_owner_cash_sources as source
    from value_investment_agent.application.research.agent_review.parent_cash_task_v3 import (
        _parent_cost_method_income,
    )

    header = "样本股份有限公司2025年年度报告"
    pages = [
        header + "\n投资收益\n成本法核算的长期股权投资收益 100.00 90.00",
        header + "\n十九、母公司财务报表主要项目注释\n一、合营企业",
        header + f"\n单位：{unit} 币种：人民币\n项目 本期发生额 上期发生额"
        + "\n成本法核算的长期股权投资收益 8.00 7.00",
        header + "\n二十、补充资料\n成本法核算的长期股权投资收益 200.00 190.00",
    ]
    if expect_error:
        with pytest.raises(ValueError, match="PARENT_TERMINAL_COST_METHOD_NOTE_HEADER_CHANGED"):
            _parent_cost_method_income(pages, source, "样本股份有限公司", "2025-12-31")
    else:
        row = _parent_cost_method_income(pages, source, "样本股份有限公司", "2025-12-31")
        assert (row["current"], row["comparative"], row["physical_page"]) == ("8.00", "7.00", 3)


def test_terminal_driver_wire_derives_cfo_without_accepting_a_model_total():
    from value_investment_agent.infrastructure.agent_runtime.provider import LLMRequest

    template = {"type": "object"}
    schema = {"properties": {"terminal": {"properties": {"policy": {
        "required": ["operating_cash", "parent_profit"],
        "properties": {"operating_cash": template, "parent_profit": template},
    }}}}}
    request = LLMRequest(
        role="terminal",
        system="Keep operating_cash distinct from the required other_operating_cash component. ",
        user=json.dumps({
            "required_fields": ["operating_cash", "parent_profit"],
            "source_context": {"facts": {"profit": {}}},
        }), output_schema=schema,
        transport_output_contract="policy has exactly these keys: operating_cash, parent_profit.",
    )
    wire = target._terminal_driver_wire(request, replace_legacy_contract=True)
    sent_fields = wire.transport_output_contract.split(".", 1)[0].split(": ", 1)[1].split(", ")
    assert sent_fields == json.loads(wire.user)["required_fields"]
    assert "operating_cash" not in sent_fields and "Keep operating_cash distinct" not in wire.system
    assert "operating_cash, parent_profit" in target._terminal_driver_wire(request).transport_output_contract
    assert "operating_cash" not in json.loads(wire.user)["required_fields"]
    terms = {
        key: dict(term(1), values=[value])
        for key, value in (("customer_cash", "100"), ("supplier_cash", "70"),
                           ("operating_tax_refunds", "0"), ("other_operating_receipts", "5"),
                           ("employee_cash_paid", "6"),
                           ("operating_tax_paid", "4"), ("other_operating_payments", "5"),
                           ("parent_profit", "25"))
    }

    def response():
        return LLMResponse(json.dumps({"terminal": {"policy": terms}}), 100, 100, "deepseek-flash")

    actual = target._merge_terminal_driver_response(response(), request)
    assert json.loads(actual.text)["terminal"]["policy"]["operating_cash"]["values"] == ["20"]
    terms["operating_cash"] = term(1)
    with pytest.raises(ValueError, match="TERMINAL_DRIVER_FIELDS_INVALID"):
        target._merge_terminal_driver_response(response(), request)
    terms.pop("operating_cash")
    terms["supplier_cash"]["values"] = ["-70"]
    with pytest.raises(ValueError, match="TERMINAL_NEGATIVE_GROSS_CASH_DRIVER"):
        target._merge_terminal_driver_response(response(), request)



def test_terminal_distribution_rejections_distinguish_profit_payout_and_reserve():
    def draft(profit, payout, reserve):
        return {"terminal": {"policy": {
            field: {"values": [value]} for field, value in {
                "parent_profit": profit, "payout_ratio": payout, "reserve_ratio": reserve,
            }.items()
        }}}

    rows = target.ParentCashTaskServiceV3._terminal_distribution_rejections({
        "bear": draft("10", ".5", ".1"),
        "base": draft("11", "0.00", ".1"),
        "bull": draft("0", ".7", "1"),
    })
    assert {row["scenario"]: row["reasons"] for row in rows} == {
        "base": ["NONPOSITIVE_PAYOUT_ASSUMPTION"],
        "bull": ["NONPOSITIVE_PARENT_PROFIT", "NO_DISTRIBUTABLE_PROFIT_AFTER_RESERVE"],
    }




def test_v3_assembly_consumes_pinned_distribution(task, monkeypatch):
    service, _ = task
    spec_binding = {"path": "runtime/spec.json", "sha256": "b" * 64}
    distribution = {"path": "runtime/distribution.json", "sha256": "c" * 64}
    seen = []

    def assemble(**kwargs):
        seen.append(kwargs)
        return {"action": "no_order"}

    monkeypatch.setattr(target, "assemble_parent_cash_drafts_v2", assemble)
    spec = {"spec_binding": spec_binding}
    assert service._assemble(spec, {}, NOW)["action"] == "no_order"
    service._assemble({**spec, "implemented_distribution_receipt_binding": distribution}, {}, NOW)
    assert "implemented_distribution" not in seen[0]
    assert seen[1]["implemented_distribution"] == distribution



@pytest.mark.parametrize(("amount", "category", "error"), [
    ("0", "NONE", None),
    ("15", "NON_FINANCING", None),
    ("15", "FINANCING_INTEREST", "DUPLICATES_FINANCING_INTEREST:2027"),
    ("15", "NONE", "CLASSIFICATION_INVALID"),
    ("0", "NON_FINANCING", "CLASSIFICATION_INVALID"),
])
def test_mandatory_cash_categories_are_checked_before_cash_compilation(amount, category, error):
    body = {"years": [2027], "series": {"other_mandatory_cash": {
        "values": [amount], "cash_class_by_year": [category],
    }}}
    response = LLMResponse(json.dumps(body), 100, 100, "deepseek-flash")
    normalize = target.ParentCashTaskServiceV3._strip_mandatory_cash_classification
    if error:
        with pytest.raises(ValueError, match=error):
            normalize(response)
    else:
        parsed = json.loads(normalize(response).text)
        assert parsed["series"]["other_mandatory_cash"] == {"values": [amount]}
    assert json.loads(response.text) == body


def test_flat_terminal_review_requires_exact_single_complete_object():
    terminal = {
        "policy": {}, "remaining_scheduled_events": [], "max_transition_years": 20,
        "financing": None, "rationale": "TEST_ONLY", "counter_evidence": "TEST_ONLY",
        "reopen_condition": "TEST_ONLY",
    }
    full = {**terminal, "cost_of_equity": {}}
    original = json.dumps(full)
    response = LLMResponse(original, 100, 100, "deepseek-flash")
    normalized = target._unpack_flat_terminal_review_response(response)
    assert json.loads(normalized.text) == {"terminal": terminal, "cost_of_equity": {}}
    assert response.text == original
    # A prematurely closed outer object followed by duplicated terminal metadata.
    trailing = original + ",\"financing\":null}"
    with pytest.raises(ValueError, match="TERMINAL_REVIEW_INVALID_JSON"):
        target._unpack_flat_terminal_review_response(
            LLMResponse(trailing, 100, 100, "deepseek-flash"))
    with pytest.raises(ValueError, match="TERMINAL_REVIEW_FIELDS_INVALID"):
        target._unpack_flat_terminal_review_response(
            LLMResponse(normalized.text, 100, 100, "deepseek-flash"))



def test_scalar_terminal_review_normalizes_only_verified_gross_cash_ids():
    term = {"value": "1.25", "evidence_anchors": ["operating_tax_paid", "book"],
            "mechanism": "TEST_ONLY source-aware forecast", "counter_evidence": "Assumption may fail",
            "reopen_condition": "Recheck when annual filing arrives"}
    body = {"policy": {"operating_tax_refunds": term},
            "remaining_scheduled_events": [], "max_transition_years": 20, "financing": None,
            "rationale": "TEST_ONLY", "counter_evidence": "TEST_ONLY", "reopen_condition": "TEST_ONLY",
            "cost_of_equity": {**term, "evidence_anchors": ["book"]}}
    original = LLMResponse(json.dumps(body), 100, 100, "deepseek-flash")
    result = target._unpack_flat_terminal_review_response(
        original, verified_cash_lines={"operating_tax_paid": {}})
    converted = json.loads(result.text)["terminal"]["policy"]["operating_tax_refunds"]
    assert converted["values"] == ["1.25"]
    assert converted["evidence_anchors"] == ["cfo", "book"]
    assert "operating_tax_paid" in converted["mechanism"]
    assert json.loads(original.text) == body
    term["values"] = ["1.25"]
    with pytest.raises(ValueError, match="TERM_SOURCE_INVALID"):
        target._unpack_flat_terminal_review_response(
            LLMResponse(json.dumps(body), 100, 100, "deepseek-flash"),
            verified_cash_lines={"operating_tax_paid": {}})




def test_audited_terminal_cash_reference_excludes_investment_and_financing():
    cohort = {"observations": [{
        "period_end": "2025-12-31",
        "values_cny": {"cfo": "100", "gross_capex": "30",
                       "investment_cash": "999", "new_borrowing": "999"},
    }]}
    reference = target._audited_distribution_cash_reference(cohort, {"cash_cny": "80"})
    row, = reference["observations"]
    assert row["cash_after_gross_capex_cny"] == "70"
    assert row["headroom_after_nominal_payment_cny"] == "-10"
    assert "cash_floor" in reference["excludes"]


@pytest.mark.parametrize("closing", ["120", "121"])
def test_terminal_retained_reference_checks_reconciled_parent_profit(monkeypatch, tmp_path, closing):
    from value_investment_agent.application.research import parent_direct_owner_cash_sources as sources

    report = dict(path="runtime/quarter.pdf", sha256="a" * 64,
                  url="https://example.test/quarter.pdf", acquired_at=NOW.isoformat())
    monkeypatch.setattr(target.staged_numbered, "_load_spec",
                        lambda *_: dict(quarterly_financing_source=report, issuer_name="Issuer"))

    def read(**kwargs):
        assert kwargs["symbol"] == "600887"
        assert kwargs["sources"][0]["period_end"] == "2026-09-30"
        return {"statements": [{
            "balance_sheet": {"retained_earnings_cny": {
                "current": closing, "comparative": "100", "source_refs": {"physical_page": 12}}},
            "income": {"parent_net_profit_cny": {"current": "50", "source_refs": {"physical_page": 13}}},
            "cash_flow": {field: {"current": "40"} for field in (
                "cfo_cny", "gross_capex_cny", "mixed_distribution_interest_paid_cny")},
        }]}

    monkeypatch.setattr(sources, "read_parent_direct_owner_cash_sources", read)
    spec = dict(spec_binding={}, created_at=NOW.isoformat())
    context = dict(valuation_date="2025-12-31", symbol="600887")
    distribution = dict(total_cny="30", paid_date="2026-06-05")
    if closing == "121":
        with pytest.raises(ValueError, match="PARENT_V3_RETAINED_EARNINGS_ROLLFORWARD_UNRECONCILED"):
            target._terminal_parent_retained_reference(tmp_path, spec, context, distribution)
    else:
        result = target._terminal_parent_retained_reference(tmp_path, spec, context, distribution)
        assert result["closing_retained_cny"] == "120"
        assert result["profit_source"]["physical_page"] == 13
        assert result["classification"] == "HISTORICAL_PARENT_RETAINED_EARNINGS_NOT_CASH_OR_FUTURE_CAPACITY"


@pytest.mark.parametrize("review, payout, investment, anchor, error", [
    ("RESEARCH_PAYOUT_V3", "0.3", "1", "revenue", None),
    ("RESEARCH_PAYOUT_V4", "0", "1", "revenue", "PARENT_V3_NO_POSITIVE_SUPPORTED_TERMINAL_DISTRIBUTION"),
    ("RESEARCH_PAYOUT_V4", "0.3", "1", "revenue", "PARENT_V3_TERMINAL_INVESTMENT_CASH_ANCHOR_REQUIRED"),
    ("RESEARCH_PAYOUT_V4", "0.3", "0", "revenue", None),
    ("RESEARCH_PAYOUT_V4", "0.3", "1", "observed_receipt", None),
])
def test_terminal_investment_cash_requires_relevant_evidence(review, payout, investment, anchor, error):
    request = types.SimpleNamespace(user=json.dumps({"source_context": {"facts": {
        "revenue": {"field": "revenue"},
        "observed_receipt": {"field": "investment_income_cash_cny"},
    }}}))
    policy = {
        "parent_profit": {"values": ["10"]},
        "payout_ratio": {"values": [payout]},
        "reserve_ratio": {"values": ["0.1"]},
        "investment_cash_received": {"values": [investment], "evidence_anchors": [anchor]},
    }
    spec = dict(terminal_cash_review=review, terminal_distribution_preflight=True)
    if error is None:
        target.ParentCashTaskServiceV3._preflight_terminal(spec, request, {"terminal": {"policy": policy}})
    else:
        with pytest.raises(ValueError, match=error):
            target.ParentCashTaskServiceV3._preflight_terminal(spec, request, {"terminal": {"policy": policy}})


@pytest.mark.parametrize(("amounts", "error"), [
    (["4.00", "0.00"], None),
    (["4.01", "0.00"], "PARENT_V3_ANNUAL_INVESTMENT_RECEIPTS_UNSUPPORTED:2026"),
    (["4.00", "4.00"], "PARENT_V3_ANNUAL_INVESTMENT_RECEIPTS_UNSUPPORTED:2027"),
    (["0.00", "0.00"], "PARENT_V3_ANNUAL_INVESTMENT_RECEIPTS_BELOW_REALISED_CASH:2026"),
])
def test_base_investment_receipts_wire_uses_only_own_year_actual(task, monkeypatch, amounts, error):
    service, _ = task
    request = types.SimpleNamespace(user=json.dumps(dict(
        scenario="base", required_years=[2026, 2027], source_context=dict(
            symbol="600887", annual_investment_receipts_floor=dict(
                symbol="600887", scope=target.terminal_wire.SCOPE, currency="CNY",
                year=2026, observed_through="2026-09-30", minimum_cny="4.00")))))
    parsed = dict(years=[2026, 2027], series={"investment_cash_received": dict(values=amounts)})
    monkeypatch.setattr(target, "parse_staged_parent_cash_response", lambda *_a, **_kw: parsed)
    legacy = {"implementation_sha256": {}}
    revised = dict(legacy, base_investment_receipts_wire=target.BASE_INVESTMENT_RECEIPTS_V1)
    assert service._parse_stage(legacy, "policy", None, request, "fixture") == parsed
    if error:
        with pytest.raises(ValueError, match=error):
            service._parse_stage(revised, "policy", None, request, "fixture")
    else:
        assert service._parse_stage(revised, "policy", None, request, "fixture") == parsed


def test_v4_policy_successor_versions_only_base_policy_without_provider_call(task, monkeypatch):
    service, provider = task
    reader = target.read_parent_cash_agent_facts_v2
    floor = dict(symbol="600887", scope=target.terminal_wire.SCOPE, currency="CNY",
                 year=2026, observed_through="2026-09-30", minimum_cny="4.00")
    monkeypatch.setattr(target, "read_parent_cash_agent_facts_v2",
                        lambda **kwargs: dict(reader(**kwargs), annual_investment_receipts_floor=floor))
    binding = dict(path="runtime/spec.json", sha256="b" * 64)
    original = service.create(spec_binding=binding, request_key="old-v4-policy", now=NOW)
    provider.fail_at = 6
    failed = service.run(original["task_id"], now=NOW)
    assert "base.policy" in failed["completed_stages"]
    load = service._load

    def sealed_v4(task_id, **kwargs):
        spec, state, head = load(task_id, **kwargs)
        if task_id == original["task_id"]:
            spec = dict(spec, terminal_cash_review="RESEARCH_PAYOUT_V4")
            state = dict(state, error_code="BASE_TERMINAL_PARENT_V3_NO_POSITIVE_SUPPORTED_TERMINAL_DISTRIBUTION")
        return spec, state, head

    monkeypatch.setattr(service, "_load", sealed_v4)
    successor = service.create(spec_binding=binding, request_key="new-v4-policy", now=NOW,
                               seed_task_id=original["task_id"], replay_from_stage="base.policy")
    spec, state, _ = load(successor["task_id"])
    assert spec["base_investment_receipts_wire"] == target.BASE_INVESTMENT_RECEIPTS_V1
    assert spec["terminal_cash_review"] == "RESEARCH_PAYOUT_V4"
    assert spec["seed"]["responses"] == {key: ref for key, ref in load(original["task_id"])[1]["responses"].items()
                                         if key != "base.policy"}
    assert state["provider_requests"] == 0
    assert len(provider.calls) == 6

    complete = provider.complete

    def repeat_actual(request):
        response = complete(request)
        body = json.loads(response.text)
        body["series"]["investment_cash_received"]["values"] = ["4.00"] * 10
        return LLMResponse(json.dumps(body), response.prompt_tokens,
                           response.completion_tokens, response.model_id)

    monkeypatch.setattr(provider, "complete", repeat_actual)
    rejected = service.run(successor["task_id"], now=NOW)
    assert rejected["error_code"] == "BASE_POLICY_PARENT_V3_ECONOMIC_PARENT_V3_ANNUAL_INVESTMENT_RECEIPTS_UNSUPPORTED:2027"
    assert provider.calls[6:] == [("base", "policy")]
    assert service.read(original["task_id"])["status"] == "FAILED"


@pytest.mark.parametrize(("invalid_operating", "expected"), [
    (False, "GROSS_CAPEX_PLAN_HORIZON_MISMATCH"),
    (True, "GROSS_CAPEX_BASE_OPERATING_REPLAY_REQUIRED"),
])
def test_gross_capex_successor_checks_annual_policy_before_task_creation(
        task, monkeypatch, invalid_operating, expected):
    service, provider = task
    binding = dict(path="runtime/spec.json", sha256="b" * 64)
    original = service.create(spec_binding=binding, request_key="old-gross-capex", now=NOW)
    complete = provider.complete

    def invalid_terminal(request):
        response = complete(request)
        if len(provider.calls) == 6:
            return LLMResponse("{}", response.prompt_tokens, response.completion_tokens, response.model_id)
        return response

    monkeypatch.setattr(provider, "complete", invalid_terminal)
    failed = service.run(original["task_id"], now=NOW)
    assert "base.policy" in failed["completed_stages"]
    load = service._load

    def sealed_predecessor(task_id, **kwargs):
        spec, state, head = load(task_id, **kwargs)
        if task_id == original["task_id"]:
            spec = dict(spec, terminal_cash_review="RESEARCH_PAYOUT_V4",
                        implemented_distribution_receipt_binding=binding)
            state = dict(state, error_code="BASE_TERMINAL_PARENT_DRAFT_TERM_SOURCE_INVALID")
        return spec, state, head

    wire = service._wire

    def reject_invalid_annual_plan(spec, stage, request, *, root=None):
        if spec.get("gross_capex_plan_binding") and json.loads(request.user)["scenario"] == "base":
            if stage == "operating" and invalid_operating:
                raise ValueError("TEST_ONLY_CHANGED_OPERATING_REQUEST")
            if stage != "operating":
                assert not invalid_operating
                assert stage == "policy"
                raise ValueError("GROSS_CAPEX_PLAN_HORIZON_MISMATCH")
        return wire(spec, stage, request, root=root)

    monkeypatch.setattr(service, "_load", sealed_predecessor)
    monkeypatch.setattr(service, "_wire", reject_invalid_annual_plan)
    with pytest.raises(ValueError, match=expected):
        service.create(spec_binding=binding, request_key="new-gross-capex", now=NOW,
                       seed_task_id=original["task_id"], replay_from_stage="base.policy",
                       gross_capex_plan_binding=binding)
    assert len(provider.calls) == 6


@pytest.mark.parametrize(("change", "error"), [
    ("none", None),
    ("receipt", "PARENT_V3_CAPITAL_IR_RECEIPT_CHANGED"),
    ("original", "PARENT_V3_CAPITAL_IR_ORIGINAL_CHANGED"),
    ("excerpt", "PARENT_V3_CAPITAL_IR_EXCERPT_INVALID"),
    ("issuer", "PARENT_V3_CAPITAL_IR_EXCERPT_INVALID"),
    ("cutoff", "PARENT_V3_CAPITAL_IR_SOURCE_INVALID"),
    ("scope", "PARENT_V3_CAPITAL_EVIDENCE_Q3_INVALID"),
])
def test_base_capital_evidence_projects_dated_totals_and_separate_group_outlook(
        tmp_path, monkeypatch, change, error):
    from value_investment_agent.infrastructure.filings import pdf_text

    scope = target.terminal_wire.SCOPE
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    original = runtime / "ir.pdf"
    original.write_bytes(b"test-only original")
    low_temp = "持续地进行低温业务上的投入"
    deep_processing = "未来五年的深加工发展战略目标"
    pages = ["证券代码：600887 投资者关系活动记录表 编号：20261030"] + [""] * 5
    pages += [low_temp, deep_processing]
    if change == "issuer":
        pages[0] = pages[0].replace("600887", "600519")
    monkeypatch.setattr(pdf_text, "extract_pages", lambda path: pages)
    acquired = "2026-11-25T07:39:03+00:00"
    receipt = dict(
        symbol="600887", action="no_order", original="runtime/ir.pdf", acquired_at=acquired,
        classification="ISSUER_GROUP_MANAGEMENT_OUTLOOK_NOT_PARENT_CASH_PROOF",
        source_url=("https://dataclouds.cninfo.com.cn/shgonggao/investor/"
                    "2026/20261103/e794e53c3792fc41fc8068baba3e31fc.pdf"),
        source_sha256=target._hash(original.read_bytes()),
        findings={low_temp: dict(physical_page=7, excerpt=low_temp),
                  deep_processing: dict(physical_page=8, excerpt=deep_processing)},
    )
    if change == "excerpt":
        receipt["findings"][low_temp]["physical_page"] = 8
    path = runtime / "receipt.json"
    path.write_bytes(target._bytes(receipt))
    ir = dict(path="runtime/receipt.json", sha256=target._hash(path.read_bytes()))
    if change == "receipt":
        path.write_bytes(path.read_bytes() + b" ")
    if change == "original":
        original.write_bytes(b"changed")
    fy_source = dict(available_at="2026-04-30T00:00:00+00:00", physical_page=91)
    monkeypatch.setattr(target, "_terminal_parent_cash_history", lambda *_: dict(
        scope=scope, currency="CNY", source_refs={"gross_capex_cny": fy_source},
        observations=[dict(period_end="2025-12-31", values_cny={"gross_capex_cny": "631984543.41",
                      "mixed_distribution_interest_paid_cny": "111"})]))
    context = dict(symbol="600887", valuation_date="2025-12-31", annual_capex_floor=dict(
        symbol="600887", scope="GROUP" if change == "scope" else scope, currency="CNY",
        year=2026, period_start="2026-01-01", observed_through="2026-09-30",
        minimum_cny="1410074492.50", source_ref=dict(
            available_at="2026-11-15T00:00:00+00:00", physical_page=14)))
    arguments = dict(root=tmp_path, spec_binding={}, context=context, ir_receipt_binding=ir,
                     as_of=NOW if change == "cutoff" else datetime.fromisoformat(acquired))
    if error is not None:
        with pytest.raises(ValueError, match=error):
            target.project_base_capital_evidence_v1(**arguments)
        return

    projected = target.project_base_capital_evidence_v1(**arguments)
    assert projected["schema_version"] == target.BASE_CAPITAL_EVIDENCE_V1
    assert projected["status"] == "BLOCKED"
    assert projected["replay_from_stage"] == "base.policy"
    assert projected["affected_stages"] == ["base.policy", "base.terminal"]
    assert projected["parent_gross_capex"]["annual_observations"] == [
        {"period_end": "2025-12-31", "gross_capex_cny": "631984543.41"}]
    assert projected["parent_gross_capex"]["ytd_observation"]["gross_capex_cny"] == "1410074492.50"
    assert projected["group_management_outlook"]["findings"] == receipt["findings"]
    for field in ("maintenance_capex", "growth_capex", "interest_outside_cfo", "payout_ratio"):
        assert field not in json.dumps(projected)


@pytest.mark.parametrize(("stage", "scenario", "blocked"), [
    ("policy", "base", True), ("terminal", "base", True),
    ("operating", "base", False), ("policy", "bear", False),
])
def test_base_capital_review_blocks_request_and_cache_reconstruction(monkeypatch, stage, scenario, blocked):
    request = types.SimpleNamespace(user=json.dumps({"scenario": scenario}))
    monkeypatch.setattr(target.ParentCashTaskServiceV3, "_base_wire", lambda *_a, **_kw: request)
    historical = {"implementation_sha256": {}}
    reviewed = dict(historical, base_capital_evidence_review=target.BASE_CAPITAL_EVIDENCE_V1)
    assert target.ParentCashTaskServiceV3._wire(historical, stage, request) is request
    if blocked:
        with pytest.raises(ValueError, match="PARENT_V3_BASE_CAPITAL_EVIDENCE_REVIEW_BLOCKED"):
            target.ParentCashTaskServiceV3._wire(reviewed, stage, request)
    else:
        assert target.ParentCashTaskServiceV3._wire(reviewed, stage, request) is request
