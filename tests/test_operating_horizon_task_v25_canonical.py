"""TEST_ONLY V25 native transport.  It never invokes a paid model."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from test_operating_horizon_task_v19_generic import setup as v19_setup
from test_operating_horizon_draft_v1 import context as base_context  # noqa: F401
from test_operating_horizon_split_v8 import _annual, _cash
from value_investment_agent.application.research.agent_review import operating_horizon_task_v25_canonical as task
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse

NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)


def native_row(scenario):
    path = json.loads(_annual())["years"]["2027"]["operating_paths"][scenario]
    names = {"volume_change": "revenue_activity_volume",
             "realization_mix_change": "realization_mix_change",
             "unit_cost_change": "unit_cost_change", "fixed_cogs_share": "fixed_cogs_share",
             "opex_change": "opex_change", "surcharge_ratio": "surcharge_ratio",
             "other_pretax_cny": "other_pretax_cny"}
    drivers = [dict(driver_id=names[name], value=dict(type="range", lower=float(row["lower"]),
        upper=float(row["upper"]), unit="CNY" if name == "other_pretax_cny" else "ratio"),
        baseline_anchor_ids=row["evidence_ids"], rationale=row["rationale"])
        for name, row in path["drivers"].items()]
    capital_ids = {"investment": "capital_investment", "funding_access": "funding_access",
                   "terminal": "terminal"}
    capital = [dict(assumption_id=capital_ids[row["dimension"]],
        value=dict(type="unknown" if row["classification"] == "UNKNOWN" else "range",
                   lower=row["lower"], upper=row["upper"], unit=row["unit"]),
        baseline_anchor_ids=row["evidence_ids"], rationale=row["rationale"])
        for row in path["capital_assumptions"]]
    case = path["unit_cost_case"]
    return dict(scenario=scenario, drivers=drivers, capital_assumptions=capital,
        unit_cost_mechanism="INPUT_PRICE",
        unit_cost_case=dict(conditional_mechanism=case["mechanism"],
                            mechanism_source_ids=case["source_anchor_ids"],
                            contrary_evidence_ids=case["contrary_evidence_ids"]),
        counter_evidence=["historical cost ratio is contrary evidence"],
        reopen_condition=case["reopen_condition"])


@pytest.fixture
def setup(v19_setup, monkeypatch):
    old, source, calls = v19_setup
    monkeypatch.setattr(task, "_now", lambda value=None: value or NOW)
    service = task.OperatingHorizonTaskService(old.root, source_loader=old.source_loader,
        source_loader_version=old.source_loader_version, test_provider=old.test_provider)
    def complete(request):
        calls.append(request)
        if len(calls) <= 3:
            scenario = task.SCENARIOS[len(calls) - 1]
            return LLMResponse(json.dumps(native_row(scenario)), 100, 50, "TEST_ONLY")
        return LLMResponse(_cash(unknown=True), 100, 50, "TEST_ONLY")
    service.test_provider.complete = complete
    return service, source, calls


def test_native_three_scenarios_are_normalized_then_wait_for_cash_evidence(setup):
    service, _, calls = setup
    created = service.create(symbol="600887", request_key="TEST_V25_NATIVE", years=[2027], now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "WAITING_EVIDENCE", result
    assert result["provider_requests"] == len(calls) == 4
    assert result["stage_validated"] == ["bear", "base", "bull", "cash"]
    assert result["annual_result"]["action"] == "no_order"
    assert result["formal_eligibility"] is False


def test_native_invalid_driver_is_sealed_before_next_call(setup):
    service, _, calls = setup
    def invalid(request):
        calls.append(request)
        value = native_row("bear")
        value["drivers"][0]["driver_id"] = "invented"
        return LLMResponse(json.dumps(value), 100, 50, "TEST_ONLY")
    service.test_provider.complete = invalid
    created = service.create(symbol="600887", request_key="TEST_V25_INVALID", years=[2027], now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["provider_requests"] == len(calls) == 1
    assert result["stage_validated"] == []


def test_v25_cannot_read_v21_failed_task(setup):
    service, _, calls = setup
    created = service.create(symbol="600887", request_key="TEST_V25_CANCEL", years=[2027], now=NOW)
    assert service.cancel(created["task_id"], now=NOW)["status"] == "CANCELLED"
    assert calls == []


def test_v25_uses_full_local_schema_for_json_object_transport(setup):
    service, source, _ = setup
    created = service.create(symbol="600887", request_key="TEST_V25_SCHEMA", years=[2027], now=NOW)
    spec, state, _ = service._load(created["task_id"])
    request, _ = service._request_for_stage(spec, state, service._context(spec), "bear")
    assert request.transport_output_contract is None
    assert request.output_schema["required"] == [
        "scenario", "drivers", "capital_assumptions", "unit_cost_mechanism",
        "unit_cost_case", "counter_evidence", "reopen_condition",
    ]







@pytest.mark.parametrize("valid_source", [True, False])
def test_v25_return_plan_applies_reported_fact_provenance(tmp_path, monkeypatch, valid_source):
    from value_investment_agent.application.research import (
        operating_horizon_cash_policy_e2_v11 as shared,
        operating_horizon_cash_policy_e2_v17 as e2,
    )

    digest = "a" * 64
    original = {"evidence": [{
        "id": "filing-row", "kind": "SOURCE_BOUND_REPORTED_STATEMENT_ROW",
        "pdf_sha256": digest, "source_id": "official:" + digest,
        "physical_page": 83 if valid_source else 0, "unit": "CNY",
        "available_at": "2026-04-25T08:00:00+08:00", "period": "2025-12-31",
    }]}
    spec = {
        "source_loader_binding": {"version": e2.RETURN_PLAN_LOADER},
        "context_sha256": "b" * 64,
    }
    service = object.__new__(task.OperatingHorizonTaskService)
    service.root = tmp_path
    monkeypatch.setattr(service, "_load", lambda _: (spec, {}, {}))
    monkeypatch.setattr(service, "_context", lambda _: original)

    def consume(**kwargs):
        projected = kwargs["service"]._context(spec)
        assert projected["evidence"][0]["kind"] == "VERIFIED_REPORTED_FACT"
        return {"input_manifest": {}}

    monkeypatch.setattr(shared, "_read_bound_cash_policy_e2_input", consume)
    if not valid_source:
        with pytest.raises(ValueError, match="V25_E2_REPORTED_FACT_PROVENANCE_INVALID"):
            e2.read_v25_cash_policy_e2_input(root=tmp_path, task_id="test", now=NOW, service=service)
        return
    result = e2.read_v25_cash_policy_e2_input(root=tmp_path, task_id="test", now=NOW, service=service)
    assert result["input_manifest"]["source_kind_projection"]["evidence_ids"] == ["filing-row"]
    assert original["evidence"][0]["kind"] == "SOURCE_BOUND_REPORTED_STATEMENT_ROW"


@pytest.mark.parametrize(("term", "citations", "accepted"), [
    ("reserve_ratio", ["charter"], True),
    ("accessible_profit_ratio", ["charter"], False),
    ("accessible_profit_ratio", ["charter", "parent-cfo"], True),
    ("commitment_cash_cny", ["financing"], False),
    ("commitment_cash_cny", ["financing", "capex-contract"], True),
    ("commitment_cash_cny", ["financing", "parent-cfo"], False),
])
def test_v25_cash_constraints_require_applicable_primary_anchor(monkeypatch, term, citations, accepted):
    from value_investment_agent.application.research import operating_horizon_cash_policy_e2_v17 as e2
    from value_investment_agent.application.research.agent_review import (
        operating_cash_policy_draft_v16_generic as cash,
    )

    evidence = [
        {"id": "charter", "scope": "ISSUER_ARTICLES_RULE_TEXT"},
        {"id": "financing", "scope": "ISSUER_FINANCING_DISCLOSURE"},
        {"id": "parent-cfo", "scope": "parent"},
        {"id": "capex-contract", "scope": "parent"},
    ]
    context = {"evidence": evidence, "source_binding": {}}
    monkeypatch.setattr(cash, "candidates", lambda *_: {
        "reserve_ratio": ["charter"],
        "accessible_profit_ratio": ["charter", "parent-cfo"],
        "commitment_cash_cny": ["financing", "capex-contract"],
    })
    policy = {"2027": {"base": {"terms": {term: {"evidence_ids": citations}}}}}
    if accepted:
        e2._validate_cash_constraint_citations(policy, context)
    else:
        with pytest.raises(ValueError, match="V25_E2_CASH_TERM_REQUIRES_APPLICABLE_ANCHOR:" + term):
            e2._validate_cash_constraint_citations(policy, context)
