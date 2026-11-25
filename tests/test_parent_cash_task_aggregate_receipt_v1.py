"""Aggregate task receipts use test-only files and the frozen V2 evaluator."""
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from test_direct_owner_cash_v2 import facts, case as valuation_case
from test_direct_owner_gross_capex_v1 import case
from value_investment_agent.application.research import direct_owner_gross_capex_v1 as gross
from value_investment_agent.application.research import parent_cash_task_aggregate_receipt_v1 as target
from value_investment_agent.application.research import parent_cash_task_completion_v1 as completion
from value_investment_agent.application.research import parent_cash_task_distribution_receipt_v1 as dispatch
from value_investment_agent.application.research.parent_cash_task_alignment_v3 import _align_verified_parent_cash_task
from value_investment_agent.application.research import parent_cash_task_share_anchor_v3 as share_anchors
from value_investment_agent.valuation_models.direct_owner_cash_v2 import DirectOwnerCashValuationModel

TASK = "rt-" + "1" * 32
HEAD = {"path": "runtime/head.json", "sha256": "2" * 64}
PAID = {"path": "runtime/payment.json", "sha256": "3" * 64}
CASE = {"path": "runtime/case.json", "sha256": "5" * 64}


@pytest.fixture
def sealed_case(case, monkeypatch):
    args, _, _ = case
    root, now = args["root"], args["as_of"]
    fixture = facts(scheduled="10")
    model_facts = replace(fixture, symbol="600887", as_of=date(2026, 12, 31))
    model_scenarios = {}
    monkeypatch.setattr(completion, "datetime", SimpleNamespace(now=lambda tz: now))
    raw = {}
    for name, scenario in fixture.scenario_inputs.items():
        data = {key: deepcopy(getattr(scenario, key)) for key in
                ("opening", "years", "terminal", "ordinary_shares", "cost_of_equity", "scope", "currency")}
        data["ordinary_shares"] = str(data["ordinary_shares"])
        data["cost_of_equity"] = str(data["cost_of_equity"])
        data["years"].append(dict(deepcopy(data["years"][0]), year=2028,
                                  scheduled_owner_distribution_cny="0"))
        result = gross.arithmetic.compile_direct_owner_cash_path_v2(**data)
        raw[name] = dict(data, calculation=result)
        model_scenarios[name] = replace(scenario, symbol="600887", years=data["years"],
            forecast_roes=tuple(Decimal(row["roe_assumption"]) for row in result["annual_rows"]),
            forecast_retentions=tuple(Decimal(row["retention_assumption"]) for row in result["annual_rows"]))
    model_facts = replace(model_facts, scenario_inputs=model_scenarios)
    years = args["scenario"]["years"]
    years.append(dict(deepcopy(years[0]), year=2028, scheduled_owner_distribution_cny="0"))
    aggregate_receipt = gross.compute_gross_capex_receipt(**args)
    plan = target.legacy._write(root, root / "runtime" / "plan.json",
        dict(schema_version=gross.WIRE_VERSION, source_fingerprint="source"))
    monkeypatch.setattr(share_anchors, "read_parent_cash_agent_facts_v2", lambda **kw: dict(
        symbol="600887", valuation_date="2026-12-31",
        ordinary_shares=dict(count="100", period_end="2026-12-31", unit="shares",
                             scope="TOTAL_ISSUED_ORDINARY_SHARES", classification="FACT", source_refs=[])))
    candidate = dict(schema_version=gross.WIRE_VERSION, symbol="600887",
        gross_capex_plan_binding=plan, source_fingerprint="source", scenario_draft_sha256={"base": "draft"},
        aggregate_base_receipt=aggregate_receipt,
        other_scenarios={name: raw[name]["calculation"] for name in ("bear", "bull")})
    private = {key: candidate[key] for key in ("source_fingerprint", "scenario_draft_sha256")}
    spec = dict(task_id=TASK, mode="LIVE_PARENT_CASH_V3", created_at=now.isoformat(),
        source_fingerprint="source", gross_capex_plan_binding=plan, spec_binding={"path": "runtime/spec.json"},
        implemented_distribution_receipt_binding=PAID, implementation_sha256={})
    state = dict(task_id=TASK, status="SUCCEEDED", action="no_order", formal_eligibility=False,
        updated_at=now.isoformat(), input_sha256="input", responses=dict.fromkeys(target.legacy.STAGE_ORDER, HEAD))

    class Service:
        def __init__(self, root):
            self.root = root

        def _directory(self, task_id):
            return root / task_id

        def _lock(self, *args):
            return nullcontext()

        def _load(self, task_id):
            return spec, state, HEAD

        def _drafts(self, *args):
            return {"base": "verified"}

        def _assemble(self, *args):
            return deepcopy(candidate)

    monkeypatch.setattr(target.legacy, "ParentCashTaskServiceV3", Service)
    monkeypatch.setattr(target.legacy, "assemble_parent_cash_drafts_v2", lambda **kw: private)
    monkeypatch.setattr(target.legacy, "_package_for_candidate",
                        lambda *args: (dict(symbol="600887", research_case={},
                            point_in_time={"valuation_date": "2026-12-31", "research_as_of": "2027-11-10"},
                            dependencies={}, source_contract={}),
                            dict(scenarios=deepcopy(raw), source_bindings=[])))
    monkeypatch.setattr(dispatch, "replay_parent_owner_distribution_successor", lambda **kw:
        dict(symbol="600887", distribution={"paid_date": "2027-06-01", "total_cny": "10"},
             distribution_evidence={}))
    valuation = DirectOwnerCashValuationModel().value(model_facts, replace(valuation_case(), symbol="600887"))
    monkeypatch.setattr(target.legacy.adapter, "run_direct_owner_cash_research", lambda *args, **kwargs:
        (SimpleNamespace(valuation=valuation),
         SimpleNamespace(as_policy=lambda: dict(symbol="600887", input_sha256="private", source_contract={},
             sources=[], facts=dict(operating_inputs={"ordinary_shares": "100"},
                 scenario_inputs={name: dict(currency="CNY", ordinary_shares="100") for name in raw}),
             point_in_time={"valuation_date": "2026-12-31", "research_as_of": "2027-11-10"}))))
    monkeypatch.setattr(completion, "preflight_parent_cash_task", lambda *args: (CASE, PAID))
    inputs = dict(root=root, task_id=TASK, task_head=HEAD,
                  case_package_binding=CASE, distribution_binding=PAID, now=now)
    return inputs, Service(root), state


def test_aggregate_completion_and_history_replay_preserve_gross_and_same_task(sealed_case):
    inputs, service, _ = sealed_case
    root = inputs["root"]
    completion.seal_completed_parent_cash_task(service, TASK)
    path = completion.valuation_receipt_path(root, TASK)
    pin = {
        "path": path.relative_to(root).as_posix(), "sha256": target.sha256(path.read_bytes()).hexdigest()}
    result = dispatch.replay(root=root, receipt_binding=pin, now=inputs["now"])
    assert result["provenance"]["task_record_binding"] == HEAD
    assert result["provenance"]["task_id"] == TASK
    assert result["provenance"]["distribution_receipt_binding"] == PAID
    base = result["valuation"]["assumptions"]["scenario_calculations"]["base"]
    first = base["annual_rows"][0]
    for calculation in result["valuation"]["assumptions"]["scenario_calculations"].values():
        assert [row["scheduled_owner_distribution_cny"] for row in calculation["annual_rows"]] == ["10", "0"]
        assert all(row["scheduled_owner_distribution_cny"] == "0" for row in calculation["terminal_rows"])
    descriptor = deepcopy(result["descriptor"])
    identity = descriptor.pop("input_sha256")
    assert target.sha256(target.legacy._bytes(descriptor)).hexdigest() == identity
    assert result["input_descriptor_sha256"] == identity
    assert descriptor["facts"]["scenario_inputs"]["base"] == result["aggregate_base_receipt"]["scenario"]
    assert dispatch.replay(root=root, receipt_binding=pin, now=inputs["now"]) == result
    assert first["cash_policy"]["gross_capex_cny"] == "20"
    assert first["capex_allocation"] == "UNALLOCATED"
    assert "maintenance_capex" not in first["cash_policy"] and "growth_capex" not in first["cash_policy"]
    assert result["formal_eligibility"] is False
    aligned = _align_verified_parent_cash_task(root=root, receipt_binding=pin, result=result, now=inputs["now"])
    assert aligned["currentpricecomparison"] is False
    assert "EXACT_CANDIDATE_ALIGNMENT_BINDING_MISSING" in aligned["reason_codes"]
    bad_plan = deepcopy(result)
    bad_plan["provenance"]["gross_capex_plan_binding"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="TASK_SHARE_AGGREGATE_REPLAY_IDENTITY_MISMATCH"):
        _align_verified_parent_cash_task(root=root, receipt_binding=pin, result=bad_plan, now=inputs["now"])
    completion.seal_completed_parent_cash_task(service, TASK)
    assert target.sha256(path.read_bytes()).hexdigest() == pin["sha256"]


@pytest.mark.parametrize("failure", ["different_task", "different_head", "different_distribution", "failed"])
def test_aggregate_cannot_publish_with_different_identity_or_failed_task(sealed_case, failure):
    inputs, _, state = sealed_case
    if failure == "different_task":
        inputs["task_id"] = "rt-" + "6" * 32
    elif failure == "different_head":
        inputs["task_head"] = {"path": "runtime/other-head.json", "sha256": "6" * 64}
    elif failure == "different_distribution":
        inputs["distribution_binding"] = {"path": "runtime/other-notice.json", "sha256": "6" * 64}
    else:
        state["status"] = "FAILED"
    out = inputs["root"] / "runtime" / "rejected"
    with pytest.raises(ValueError, match="GROSS_CAPEX_F1_TASK_OR_DISTRIBUTION|PARENT_TASK_EXACT_LIVE_SUCCESS"):
        target.build(output_dir=out, **inputs)
    assert not out.exists()
