from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from value_investment_agent.application.research import parent_note_grid_terminal_service_v2 as mod
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


NOW = datetime(2026, 11, 27, tzinfo=timezone.utc)
PAID = {"event_id": "fen-2025", "distribution": {"total_cny": "8002965296.32", "paid_date": "2026-07-31"}}
EVENT = dict(event_id="fen-2025", status="CONSUMED", distribution_total_cny="8002965296.32",
             mechanism="Consumed in the annual cash path.")


def request(scenario="bear"):
    return SimpleNamespace(user=json.dumps(dict(scenario=scenario, terminal_reference_year=2035,
        forecast_closing_debt_after_annual_years={"value_cny": "0"},
        source_context={"implemented_distribution": PAID})))


def reply(**changes):
    term = dict(value="0.1", evidence_anchors=["cash"], mechanism="historical basis",
                counter_evidence="historical counter", reopen_condition="reopen if changed")
    body = dict(cost_of_equity=term, policy={"commitments_outside_capex": term},
                remaining_scheduled_events=[EVENT], max_transition_years=25, financing=None,
                rationale="Conditional terminal rationale", counter_evidence="Current evidence is limited",
                reopen_condition="Recheck after new evidence",
                prior_commitment_assessment=dict(evidence_status="INSUFFICIENT_EVIDENCE",
                                                explanation="No dated commitment schedule was identified."))
    return LLMResponse(json.dumps(dict(body, **changes)), 100, 100, "deepseek-flash")


def test_verified_consumption_is_projected_for_frozen_parser_only():
    raw = reply()
    nested = json.loads(mod._validated_response(raw, request()).text)
    assert nested["cost_of_equity"]["values"] == ["0.1"]
    assert nested["terminal"]["remaining_scheduled_events"] == []
    assert "INSUFFICIENT_EVIDENCE" in nested["terminal"]["rationale"]
    assert json.loads(raw.text)["remaining_scheduled_events"] == [EVENT]


@pytest.mark.parametrize(("changes", "code"), [
    ({"remaining_scheduled_events": []}, "CONSUMED_EVENT_REQUIRED"),
    ({"remaining_scheduled_events": [EVENT, EVENT]}, "CONSUMED_EVENT_REQUIRED"),
    ({"remaining_scheduled_events": [dict(EVENT, distribution_total_cny="0")]}, "CONSUMED_EVENT_MISMATCH"),
    ({"remaining_scheduled_events": [dict(EVENT, status="UNRESOLVED")]}, "UNRESOLVED_SCHEDULED_EVENTS"),
    ({"max_transition_years": {"value": "25"}}, "TRANSITION_YEARS_INVALID"),
    ({"prior_commitment_assessment": None}, "PRIOR_COMMITMENT_ASSESSMENT_REQUIRED"),
])
def test_terminal_contract_rejects_bad_events_and_shapes(changes, code):
    with pytest.raises(ValueError, match=code):
        mod._validated_response(reply(**changes), request())


def test_duplicate_valuation_field_is_not_erased():
    raw = reply()
    text = raw.text.replace('"max_transition_years": 25', '"max_transition_years": 25, "max_transition_years": 20')
    with pytest.raises(ValueError, match="CONFLICTING_JSON_KEY"):
        mod._validated_response(replace(raw, text=text), request())


def test_unverified_prior_commitment_is_counterevidence_not_a_terminal_gate():
    spec = {"terminal_response_wire": mod.WIRE, "prior_rejected_commitment_observation": {"amount_cny": "300000000"}}
    policy = {key: {"values": ["0"]} for key in
              ("debt_repayment", "new_borrowing", "interest_outside_cfo", "commitments_outside_capex")}
    parsed = {"terminal": {"policy": policy, "financing": None}}
    mod.ParentCashService._preflight_terminal(spec, request(), parsed)
    policy["commitments_outside_capex"]["values"] = ["300000000"]
    with pytest.raises(ValueError, match="FINITE_COMMITMENT_IN_TERMINAL"):
        mod.ParentCashService._preflight_terminal(spec, request(), parsed)


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
    parent = {mod.frozen.grid.MARKER: mod.frozen.grid.VERSION, "terminal_response_wire": mod.frozen.WIRE,
              "seed": {"task_id": ancestor, "head": ancestor_head, "responses": accepted},
              "mode": "LIVE_PARENT_CASH_V3", "spec_binding": binding, "case_package_binding": case,
              "implemented_distribution_receipt_binding": paid, "created_at": NOW.isoformat(),
              "source_fingerprint": "source", "ancestor_spend": "0.10",
              "config": {"max_run_cost": "10", "max_completion_tokens_cap": 2048}}
    state = dict(status="FAILED", error_code=mod.ERROR, responses=accepted, returned_responses=[returned],
                 settled_cost="0.035", reserved_cost="0",
                 reservations={reservation: {"scenario": "bear.terminal", "status": "SETTLED"}})
    raw = json.loads(reply().text)
    raw.pop("prior_commitment_assessment")
    raw["policy"]["commitments_outside_capex"]["value"] = "300000000.00"
    original_request = request()
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
            return {}, {"settled_cost": "0.10"}, ancestor_head
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
    monkeypatch.setattr(service, "_context", lambda *args: {"symbol": "600809"})
    monkeypatch.setattr(service, "_stage_outputs", verify)
    monkeypatch.setattr(service, "_wire", lambda spec, stage, req, **kwargs: req)
    monkeypatch.setattr(service, "_bound", lambda ref: packet)
    monkeypatch.setattr(service, "_save", save)
    monkeypatch.setattr(service, "_view", lambda spec, child, *args: child)
    monkeypatch.setattr(mod.frozen.grid, "staged_parent_cash_request_v3", reconstruct)
    monkeypatch.setattr(completion, "preflight_parent_cash_task", lambda *args, **kwargs: (case, paid))

    if change:
        with pytest.raises(ValueError, match="SEALED_SHAPE_REQUIRED|ANCESTOR_SPEND_MISMATCH"):
            service.continue_bear_terminal_v2(predecessor, binding, now=NOW)
        assert saved == []
    else:
        first = service.continue_bear_terminal_v2(predecessor, binding, now=NOW)
        assert service.continue_bear_terminal_v2(predecessor, binding, now=NOW) == first
        assert len(saved) == 1 and saved[0]["ancestor_spend"] == "0.135"
        assert saved[0]["prior_rejected_commitment_observation"]["amount_cny"] == "300000000.00"
        assert saved[0]["implementation_sha256"] == mod.implementation()
        assert first["responses"] == accepted and first["provider_requests"] == 0



def test_v2_request_uses_note_grid_policy_names_and_explicit_types(monkeypatch):
    policy = ["operating_cash", "commitments_outside_capex", "interest_outside_cfo"]
    schema = dict(required=["policy", "financing", "max_transition_years", "remaining_scheduled_events"],
                  properties={"policy": {"required": policy}})
    from dataclasses import dataclass

    @dataclass
    class FlatRequest:
        user: str
        output_schema: dict
        transport_output_contract: str

    flat = FlatRequest(request().user, schema, "Use all seven gross parent cash drivers.")
    monkeypatch.setattr(mod.frozen.grid.native, "_flat_terminal_review_request", lambda *a, **k: flat)
    result = mod._terminal_wire(request(), {"sha256": "a" * 64}, {"amount_cny": "300000000.00"})
    fields = result.output_schema["properties"]
    assert fields["max_transition_years"]["type"] == "integer"
    assert fields["financing"]["anyOf"][1]["additionalProperties"] is False
    assert fields["remaining_scheduled_events"]["items"]["type"] == "object"
    assert all(key in result.transport_output_contract for key in policy)
    assert "seven gross" not in result.transport_output_contract


def test_financing_shape_cannot_replace_existing_economic_check():
    spec = {"terminal_response_wire": mod.WIRE}
    draft = request()
    data = json.loads(draft.user)
    data["forecast_closing_debt_after_annual_years"]["value_cny"] = "100"
    draft.user = json.dumps(data)
    policy = {key: {"values": ["1"]} for key in
              ("debt_repayment", "new_borrowing", "interest_outside_cfo")}
    parsed = {"terminal": {"policy": policy, "financing": {"value": "0"}}}
    with pytest.raises(ValueError, match="TERMINAL_TYPED_FINANCING_REJECTED"):
        mod.ParentCashService._preflight_terminal(spec, draft, parsed)
    parsed["terminal"]["financing"] = dict(mode="CONSTANT_DEBT_REFINANCING",
        rationale="Conditional rollover only", counter_evidence="No lender approval",
        reopen_condition="Reopen on verified maturity", coverage=dict(
            interest_outside_cfo=True, debt_scope="ALL_EXISTING_TERMINAL_DEBT"))
    mod.ParentCashService._preflight_terminal(spec, draft, parsed)
    policy["interest_outside_cfo"]["values"] = ["0"]
    with pytest.raises(ValueError, match="TERMINAL_CASH_INTEREST_REQUIRED"):
        mod.ParentCashService._preflight_terminal(spec, draft, parsed)
