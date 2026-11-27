"""Offline coverage of terminal-wire dispatch, cold verification and economic refusal."""
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from value_investment_agent.application.research import parent_cash_task_completion_v1 as completion
from value_investment_agent.application.research import parent_note_grid_task_receipt_v2 as receipt
from test_parent_note_grid_task_dispatch_v1 import FixtureProvider, retained, write

NOW = datetime.now(timezone.utc)
TASK = "rt-" + "f" * 32
HEAD = {"sha256": "1" * 64}
CASE = {"path": "runtime/case.json", "sha256": "2" * 64}
PAID = {"path": "runtime/distribution.json", "sha256": "3" * 64}


def service_head(root, wire):
    spec = dict(mode="LIVE_PARENT_CASH_V3", created_at=NOW.isoformat(),
                spec_binding=CASE, case_package_binding=CASE, implemented_distribution_receipt_binding=PAID,
                terminal_response_wire=wire, **{receipt.v1.MARKER: receipt.v1.VERSION})
    state = dict(status="SUCCEEDED", action="no_order", formal_eligibility=False, updated_at=NOW.isoformat(),
                 responses=dict.fromkeys(receipt.v1.legacy.STAGE_ORDER))
    return SimpleNamespace(root=root, _directory=lambda _: root/"runtime"/TASK,
                           _lock=lambda *args: nullcontext(), _load=lambda _: (spec, state, HEAD)), spec, state


@pytest.mark.parametrize("wire,builder", [("NOTE_GRID_FLAT_TERMINAL_V3", "build_note_grid_receipt_v3"),
    (receipt.terminal.WIRE, "build_note_grid_receipt_v2"),
    (receipt.terminal.frozen.WIRE, "build_note_grid_receipt"), (None, "build_note_grid_receipt")])
def test_completion_selects_exact_builder_before_publication(tmp_path, monkeypatch, wire, builder):
    service, _, _ = service_head(tmp_path, wire)
    monkeypatch.setattr(completion, "preflight_parent_cash_task", lambda *_: (CASE, PAID))
    def reject(**args):
        assert (args["task_id"], args["task_head"], args["case_package_binding"],
                args["distribution_binding"]) == (TASK, HEAD, CASE, PAID)
        raise ValueError("ECONOMIC_REFUSAL")
    monkeypatch.setattr(completion, builder, reject)
    with pytest.raises(ValueError, match="ECONOMIC_REFUSAL"):
        completion.seal_completed_parent_cash_task(service, TASK)
    receipt_path = completion.valuation_receipt_path(tmp_path, TASK)
    assert not receipt_path.exists() and not list(receipt_path.parent.rglob("result.json"))
    assert completion.read_valuation_publication(tmp_path, TASK, HEAD)["valuation_blockage"]["reason_code"] == "ECONOMIC_REFUSAL"


@pytest.mark.parametrize("fault,code", [("failed", "EXACT_LIVE_SUCCESS"), ("test", "EXACT_LIVE_SUCCESS"),
    ("incomplete", "EXACT_LIVE_SUCCESS"), ("changed_head", "EXACT_LIVE_SUCCESS"),
    ("old_wire", "V2_TERMINAL_RECEIPT_INPUT"), ("case", "V2_TERMINAL_RECEIPT_INPUT"),
    ("distribution", "V2_TERMINAL_RECEIPT_INPUT"), ("unverified_debt", receipt.terminal.BASE_BLOCKER)])
def test_no_result_for_ineligible_task(tmp_path, monkeypatch, fault, code):
    service, spec, state = service_head(tmp_path, receipt.terminal.WIRE)
    monkeypatch.setattr(receipt.terminal, "ParentCashService", lambda _: service)
    head, case, paid = HEAD, CASE, PAID
    if fault == "failed":
        state.update(status="FAILED", error_code=receipt.terminal.BASE_BLOCKER)
    elif fault == "test":
        spec["mode"] = "TEST_ONLY_PARENT_CASH_V3"
    elif fault == "incomplete":
        del state["responses"]["bull.terminal"]
    elif fault == "changed_head":
        head = {"sha256": "0" * 64}
    elif fault == "old_wire":
        spec["terminal_response_wire"] = receipt.terminal.frozen.WIRE
    elif fault == "case":
        case = PAID
    elif fault == "distribution":
        paid = CASE
    else:
        spec["policy_capital_basis"] = {"scope": "ALL_PARENT_LIABILITIES_UPPER_BOUND_NOT_FINANCING_FACT"}
    output = tmp_path/"runtime"/"attempt"
    with pytest.raises(ValueError, match=code):
        receipt.build(root=tmp_path, output_dir=output, now=NOW, task_id=TASK, task_head=head,
                      case_package_binding=case, distribution_binding=paid)
    assert not output.exists()


@pytest.mark.parametrize("schema,reason", [("parent-note-grid-task-receipt-v3", "NOTE_GRID_V3_RECEIPT_IMPLEMENTATION_CHANGED"),
    (receipt.SCHEMA, "NOTE_GRID_V2_RECEIPT_IMPLEMENTATION_CHANGED"),
    (receipt.v1.SCHEMA, "NOTE_GRID_RECEIPT_IMPLEMENTATION_CHANGED")])
def test_exported_reader_enforces_own_version_before_opening_result(tmp_path, schema, reason):
    bad = write(tmp_path, "invalid-header.json", {"schema_version": schema, "implementation_sha256": {}})
    with pytest.raises(ValueError, match=reason):
        completion.replay_task_receipt(root=tmp_path, receipt_binding=bad, now=NOW)


@pytest.mark.parametrize("fault", ["unsettled", "duplicate_stage", "misbound_response", "inherited_as_new", "omitted_call"])
def test_terminal_response_charge_link_refuses_mismatched_settlement(tmp_path, fault):
    service, spec, state = service_head(tmp_path, receipt.terminal.WIRE)
    spec.update(task_id=TASK, seed={"responses": {s: {} for s in receipt.terminal.frozen.PREFIX}})
    charges = {}
    for stage in set(state["responses"]) - set(spec["seed"]["responses"]):
        reservation = sha256(stage.encode()).hexdigest()
        charges[reservation] = dict(scenario=stage, status="SETTLED")
        state["responses"][stage] = {"path": f"runtime/{TASK}/response-{reservation}.json"}
    state.update(reservations=charges, provider_requests=7, new_llm_calls=7, reserved_cost="0")
    receipt._settled_responses(service, spec, state)
    charge = charges[sha256(b"bear.terminal").hexdigest()]
    if fault == "unsettled":
        charge["status"] = "RESERVED"
    elif fault == "duplicate_stage":
        charge["scenario"] = "base.terminal"
    elif fault == "misbound_response":
        state["responses"]["bear.terminal"] = state["responses"]["bull.terminal"]
    elif fault == "inherited_as_new":
        charge["scenario"] = "bear.operating"
    else:
        state["new_llm_calls"] = 6
    with pytest.raises(ValueError, match="TERMINAL_SETTLEMENT_MISMATCH"):
        receipt._settled_responses(service, spec, state)
    assert not completion.valuation_receipt_path(tmp_path, TASK).exists()


class TerminalProvider(FixtureProvider):
    def complete(self, request):
        response = super().complete(request)
        payload = json.loads(request.user)
        if (payload["scenario"], payload["stage"]) != ("bear", "terminal"):
            return response
        if "terminal_response_fields" not in payload:
            return replace(response, text='{"terminal": {}},"cost_of_equity":{}')
        body = json.loads(response.text)
        flat = dict(body["terminal"], cost_of_equity=body["cost_of_equity"])
        if "prior_rejected_commitment_observation" not in payload:
            term = flat["policy"]["commitments_outside_capex"]
            term["value"] = term.pop("values")[0]
        else:
            event = payload["source_context"]["implemented_distribution"]
            flat.update(remaining_scheduled_events=[dict(event_id=event["event_id"], status="CONSUMED",
                distribution_total_cny=event["distribution"]["total_cny"], mechanism="Included once in the annual path.")],
                prior_commitment_assessment=dict(evidence_status="INSUFFICIENT_EVIDENCE",
                    explanation="No dated terminal commitment was established in this fixture."))
        return replace(response, text=json.dumps(flat))


def test_reopen_valid_test_child_and_consume_shared_valuation_without_live_receipt(retained):
    root, source, now = retained
    spec_pin = write(root, "receipt-v2-test-spec.json", source)
    template = "runtime/600809-public-report-sources-20261127/v3-case-template-fenjiu-historical-v1.json"
    case = dict(path=template, sha256=sha256((root/template).read_bytes()).hexdigest())
    paid = source["implemented_distribution_receipt_binding"]
    entry = dict(symbol=source["symbol"], spec_binding=spec_pin, case_package_binding=case,
                 implemented_distribution_receipt_binding=paid)
    (root/"config"/"parent-cash-task-case-bindings-v1.json").write_text(json.dumps(dict(
        schema_version="parent-cash-task-case-bindings-v1", specs={spec_pin["sha256"]:entry})), encoding="utf-8")
    provider = TerminalProvider()
    worker = receipt.terminal.ParentCashService(root, test_provider=provider)
    first = worker.create(spec_binding=spec_pin, request_key="test-v2-receipt", now=now)["task_id"]
    assert worker.run(first)["error_code"] == receipt.terminal.frozen.ERROR
    second = worker.continue_terminal(first, spec_pin)["task_id"]
    assert worker.run(second)["error_code"] == receipt.terminal.ERROR
    child = worker.continue_bear_terminal_v2(second, spec_pin)["task_id"]
    assert worker.run(child)["status"] == "SUCCEEDED"
    other = receipt.terminal.ParentCashService(root, test_provider=TerminalProvider())
    reopened = other.read(child)
    assert reopened["provider_requests"] == 7 and reopened["new_llm_calls"] == 0
    spec, state, head = other._load(child)
    completed = datetime.fromisoformat(state["updated_at"])
    provenance = dict(task_id=child, case_package_binding=case, spec_binding=spec_pin,
        source_adapter_version=receipt.v1.VERSION, terminal_response_wire=receipt.terminal.WIRE,
        task_receipt_schema=receipt.SCHEMA, distribution_receipt_binding=paid)
    candidate = receipt._reopen_candidate(other, spec, state, completed)
    assert candidate == reopened["candidate"]
    result = receipt._value_candidate(root, candidate, case, child, head, completed, provenance)
    contract = result["descriptor"]["source_contract"]
    assert (contract["schema_version"], contract["task_receipt_schema"], contract["terminal_response_wire"]) == (
        receipt.v1.SCHEMA, receipt.SCHEMA, receipt.terminal.WIRE)
    assert result["adoptable_valuation"] is False and result["formal_eligibility"] is False
    assert result["valuation"]["status"] == "conditional_research_only"
    assert len(result["valuation"]["assumptions"]["scenario_calculations"]) == 3
    assert len(provider.calls) == 11 and other.test_provider.calls == []
    completion.seal_completed_parent_cash_task(other, child)
    with pytest.raises(ValueError, match="EXACT_LIVE_SUCCESS"):
        receipt.execute(root=root, task_id=child, task_head=head, case_package_binding=case,
                        distribution_binding=paid, now=datetime.now(timezone.utc))
    assert not completion.valuation_receipt_path(root, child).exists()
