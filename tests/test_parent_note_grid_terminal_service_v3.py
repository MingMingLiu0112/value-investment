from contextlib import nullcontext
from dataclasses import dataclass, replace
from decimal import Decimal
import json

import pytest

from test_parent_note_grid_terminal_service_v2 import NOW, reply, request
from value_investment_agent.application.research import parent_note_grid_terminal_service_v3 as mod


@pytest.mark.parametrize(("debt", "expected"), [("0", "null"), ("18233484577.18", "object")])
def test_financing_type_and_counterevidence_are_part_of_wire(debt, expected):
    @dataclass
    class Flat:
        user: str
        output_schema: dict
        transport_output_contract: str

    fields = {"financing": {"anyOf": [{"type": "null"}, {"type": "object"}]}, "cost_of_equity": {"type": "object"}}
    wire = Flat(json.dumps({"forecast_closing_debt_after_annual_years": {"value_cny": debt}}),
                {"required": list(fields), "properties": fields}, "")
    result = mod._review_wire(wire, {"response_binding": {"sha256": "a" * 64}})
    assert result.output_schema["properties"]["financing"]["type"] == expected
    assert set(result.output_schema["properties"]["counterevidence_review"]["required"]) == set(mod.REVIEW_KEYS)
    assert json.loads(result.user)["required_return_review"]["classification"] == "CONDITIONAL_RESEARCH_HURDLE"


def test_response_requires_each_explanation():
    service = object.__new__(mod.ParentCashService)
    with pytest.raises(ValueError, match="COUNTEREVIDENCE_REQUIRED"):
        service._parse_stage({"terminal_response_wire": mod.WIRE}, "terminal", reply(), request(), "source")


def test_run_stops_before_base_charge_and_retains_accepted_bear(monkeypatch):
    spec = {"terminal_response_wire": mod.WIRE, "policy_capital_basis": {"scope": "UPPER_BOUND"}}
    responses = dict.fromkeys(mod.frozen.PREFIX | {"bear.terminal"}, {"sha256": "sealed"})
    state = dict(status="RUNNING", responses=responses, reserved_cost="0",
                 reservations={"terminal": {"scenario": "bear.terminal", "status": "SETTLED"}})
    service = object.__new__(mod.ParentCashService)
    monkeypatch.setattr(service, "_directory", lambda _: None)
    monkeypatch.setattr(service, "_lock", lambda *args: nullcontext())
    monkeypatch.setattr(service, "_load", lambda _: (spec, state, "head"))
    monkeypatch.setattr(service, "_verify_charges", lambda saved: saved is state)
    monkeypatch.setattr(service, "_save", lambda *args, **changes: (dict(state, **changes), "failed-head"))
    monkeypatch.setattr(service, "_view", lambda spec, saved, *args: saved)
    monkeypatch.setattr(mod.frozen.ParentCashService, "_wire", lambda self, spec, stage, draft, **kwargs: draft)

    def inherited_run(self, task_id, **kwargs):
        self._wire(spec, "operating", request("base"))
        pytest.fail("Base must stop before the reservation and provider call")

    monkeypatch.setattr(mod.frozen.ParentCashService, "run", inherited_run)
    assert service._wire({"terminal_response_wire": mod.frozen.WIRE}, "operating", request("base")).user
    stopped = service.run("task", now=NOW)
    assert stopped["status"] == "FAILED" and stopped["error_code"] == mod.BASE_BLOCKER
    assert stopped["responses"] == responses and stopped["reservations"] == state["reservations"]



@pytest.mark.parametrize("change", [None, "request_digest", "ancestor_spend"])
def test_creation_binds_two_generations_and_reuses_only_accepted_stages(tmp_path, monkeypatch, change):
    from value_investment_agent.application.research import parent_cash_task_completion_v1 as completion

    service = object.__new__(mod.ParentCashService)
    service.root = tmp_path
    service.test_provider = None
    predecessor, ancestor = "rt-" + "1" * 32, "rt-" + "2" * 32
    head, ancestor_head = {"sha256": "1" * 64}, {"sha256": "2" * 64}
    binding, case, paid = {"sha256": "3" * 64}, {"sha256": "4" * 64}, {"sha256": "5" * 64}
    accepted = {stage: {"path": f"ancestor/{stage}"} for stage in mod.frozen.PREFIX}
    reservation = "6" * 64
    returned = {"path": f"runtime/{predecessor}/response-{reservation}.json", "sha256": "7" * 64}
    parent = {"task_id": predecessor, mod.frozen.grid.MARKER: mod.frozen.grid.VERSION, "terminal_response_wire": mod.v2.WIRE,
              "seed": {"task_id": ancestor, "head": ancestor_head, "responses": accepted},
              "mode": "LIVE_PARENT_CASH_V3", "spec_binding": binding, "case_package_binding": case,
              "implemented_distribution_receipt_binding": paid, "created_at": NOW.isoformat(),
              "source_fingerprint": "source", "ancestor_spend": "0.10",
              "config": {"max_run_cost": "10", "max_completion_tokens_cap": 2048}}
    state = dict(status="FAILED", error_code=mod.v2.ERROR, responses=accepted, returned_responses=[returned],
                 settled_cost="0.035", reserved_cost="0",
                 reservations={reservation: {"scenario": "bear.terminal", "status": "SETTLED"}})
    raw = json.loads(reply().text)
    raw["cost_of_equity"] = "0.10"
    for field, value in (("interest_outside_cfo", "8823431.84"), ("new_borrowing", "0"), ("debt_repayment", "0")):
        raw["policy"][field] = {"values": [value]}
    raw["policy"]["commitments_outside_capex"]["value"] = "300000000.00"
    original_request = request()
    payload = json.loads(original_request.user)
    payload["forecast_closing_debt_after_annual_years"]["value_cny"] = "18233484577.18"
    original_request.user = json.dumps(payload)
    packet = dict(action="no_order", scenario="bear.terminal", source_fingerprint="source",
                  request_sha256=mod._hash(mod._bytes(original_request.__dict__)),
                  response=replace(reply(), text=json.dumps(raw)).__dict__)
    if change == "request_digest":
        packet["request_sha256"] = "0" * 64
    elif change == "ancestor_spend":
        parent["ancestor_spend"] = "0"

    stored = {}
    saved = []

    def load(task):
        if task == predecessor:
            return parent, state, head
        if task == ancestor:
            return {"task_id": ancestor, "seed": {"task_id": "root", "head": "root-head"}, "ancestor_spend": "0.065"}, {"settled_cost": "0.035"}, ancestor_head
        if task == "root":
            return {"task_id": "root"}, {"settled_cost": "0.065"}, "root-head"
        return stored[task]

    def save(spec, child, _, now):
        stored[spec["task_id"]] = (spec, child, {"sha256": "new"})
        saved.append(spec)
        return child, {"sha256": "new"}

    def reconstruct(**kwargs):
        assert kwargs["prior_drafts"] == {"operating": {}, "policy": {}}
        assert kwargs["generated_at"] == NOW
        return original_request

    def verify(spec, current, *args, **kwargs):
        assert current["responses"] == accepted
        if spec["terminal_response_wire"] == mod.WIRE:
            assert spec["seed"] == {"task_id": predecessor, "head": head, "responses": accepted}
        return {"bear": {"operating": {}, "policy": {}}}

    monkeypatch.setattr(service, "_directory", lambda task: tmp_path / "runtime" / task)
    monkeypatch.setattr(service, "_lock", lambda *args: nullcontext())
    monkeypatch.setattr(service, "_load", load)
    monkeypatch.setattr(service, "_implementation_matches", lambda spec: True)
    monkeypatch.setattr(service, "_verify_charges", lambda s: None)
    monkeypatch.setattr(service, "_context", lambda *args: {"symbol": "600809"})
    monkeypatch.setattr(service, "_stage_outputs", verify)
    monkeypatch.setattr(service, "_wire", lambda spec, stage, req, **kwargs: req)
    monkeypatch.setattr(service, "_bound", lambda ref: packet)
    monkeypatch.setattr(service, "_save", save)
    monkeypatch.setattr(service, "_view", lambda spec, child, *args: child)
    monkeypatch.setattr(mod.frozen.grid, "staged_parent_cash_request_v3", reconstruct)
    monkeypatch.setattr(completion, "preflight_parent_cash_task", lambda *args, **kwargs: (case, paid))

    if change:
        with pytest.raises(ValueError, match="REJECTED_RESPONSE_REQUIRED|CHAIN_SPEND_MISMATCH"):
            service.continue_bear_terminal_v3(predecessor, binding, now=NOW)
        assert saved == []
    else:
        first = service.continue_bear_terminal_v3(predecessor, binding, now=NOW)
        assert service.continue_bear_terminal_v3(predecessor, binding, now=NOW) == first
        assert len(saved) == 1 and saved[0]["ancestor_spend"] == "0.135"
        assert round(Decimal(saved[0]["sealed_counterevidence"]["implied_annual_interest_percent"]), 4) == Decimal("0.0484")
        assert saved[0]["sealed_counterevidence"]["terminal_commitments_cny"] == "300000000.00"
        assert saved[0]["implementation_sha256"] == mod.implementation()
        assert first["responses"] == accepted and first["provider_requests"] == 0
