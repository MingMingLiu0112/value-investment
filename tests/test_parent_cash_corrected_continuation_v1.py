"""Seven native stages after independently verified annual Bear inputs, without live calls."""
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_parent_cash_task_v3 import task, NOW
from test_parent_cash_task_aggregate_receipt_v1 import case, sealed_case, HEAD, PAID, TASK

from value_investment_agent.application.research import parent_cash_corrected_continuation_v1 as cont
from value_investment_agent.application.research import parent_cash_corrected_receipt_v1 as publication
from value_investment_agent.application.research import parent_cash_task_completion_v1 as completion
from value_investment_agent.presentation.web_api import parent_cash_history_routes as routes


@pytest.fixture
def prefix(task, monkeypatch):
    native_service, provider = task
    root = native_service.root
    svc = cont.ContinuationService(root, test_provider=provider)
    spec_binding = dict(path="runtime/spec.json", sha256="1"*64)
    parent = native_service.create(spec_binding=spec_binding, now=NOW, request_key="test-annual-source")
    parent_id = parent["task_id"]
    provider.fail_at = 3
    native_service.run(parent_id, now=NOW)
    spec, state, head = native_service._load(parent_id)
    ctx = native_service._context(spec, NOW)
    annual = native_service._stage_outputs(spec, state, NOW, verified_context=ctx)["bear"]
    assert set(annual) == {"operating", "policy"}
    terminal = cont.correction._stage_request(svc, spec, ctx, "terminal", annual)
    wire = svc._wire(spec, "terminal", terminal, root=root)
    digest = cont.correction._digest
    folder = cont.correction._folder(svc, parent_id)
    folder.mkdir(parents=True)
    intent = dict(original_request={"user": '{"source_context":{}}'}, correction_request={"user":"test repair"})
    response = dict(response={"text": json.dumps(annual["policy"])}, correction_request_sha256=digest(intent["correction_request"]))
    receipt = dict(schema_version=cont.correction.VERSION, task_id=parent_id, status="CORRECTION_VERIFIED",
        stage="bear.policy", next_stage="bear.terminal", action="no_order", formal_eligibility=False, parent_head=head,
        registered_spec=spec_binding, original_response=state["responses"]["bear.policy"],
        operating_response=state["responses"]["bear.operating"], original_request_sha256=digest(intent["original_request"]),
        intent_sha256=digest(intent), correction_response_sha256=digest(response), settled_cost_cny="0.001",
        correction_request_sha256=response["correction_request_sha256"], next_request_sha256=digest(vars(wire)))
    dispatch = {k: receipt[k] for k in ("intent_sha256", "correction_request_sha256")}
    for name, doc in (("intent",intent), ("dispatch",dispatch), ("response",response), ("receipt",receipt)):
        cont.correction._put(folder / (name + ".json"), doc)
    pin = digest(receipt)
    def replay(service, identifier, failed, sha):
        assert identifier == parent_id and sha == pin and failed == receipt["original_response"]["sha256"]
        return deepcopy(annual), wire
    # Correction v1 has its own full replay tests; exercise its downstream interface here.
    monkeypatch.setattr(cont.correction, "replay_for_terminal", replay)
    load = svc._load
    def with_distribution(identifier, **kwargs):
        original, record, version = load(identifier, **kwargs)
        if identifier == parent_id:
            original = dict(original, implemented_distribution_receipt_binding=PAID)
        return original, record, version
    monkeypatch.setattr(svc, "_load", with_distribution)
    provider.calls.clear()
    provider.fail_at = None
    return SimpleNamespace(service=svc, provider=provider, parent_id=parent_id, pin=pin, binding=spec_binding,
                           receipt=receipt, folder=folder, head=head, state=state, wire=wire)


def test_company_continuation_runs_only_seven_actual_requests(prefix, monkeypatch):
    x = prefix
    root = x.service.root
    monkeypatch.setattr(routes, "resolve_research_task_root", lambda _: root)
    monkeypatch.setattr(routes, "ParentCashTaskServiceV3", lambda _: x.service)
    monkeypatch.setattr(routes, "authorize", lambda *a, **kw: None)
    monkeypatch.setattr(routes, "registered_cash_task_spec", lambda service, symbol: x.binding)
    app = FastAPI()
    routes.register_parent_cash_history_routes(app, project=root, sessions=None, port=8001)
    client = TestClient(app)
    url = "/api/v1/operating-research/parent-cash-tasks/by-company"
    body = dict(symbol="600887", continue_from_task_id=x.parent_id, policy_correction_receipt_sha256=x.pin)
    assert 128 < len(json.dumps(body)) <= 256
    for bad in (dict(body, extra=True), dict(body, policy_correction_receipt_sha256="9"*64),
                dict(body, policy_correction_receipt_sha256=["0"]), dict(body, new_run_id="a"*32)):
        assert client.post(url, json=bad).status_code == 422
    assert client.post(url, content=json.dumps(body).ljust(257)).status_code == 422
    assert client.post(url, content=json.dumps({"symbol":"600887"}).ljust(129)).status_code == 422
    assert not x.provider.calls
    response = client.post(url, json=body)
    assert response.status_code == 202, response.text
    view = response.json()
    child = view["task_id"]
    assert child == cont._child_id(x.parent_id, x.pin) and child != x.parent_id
    assert view["status"] == "QUEUED" and view["reused_stages"] == ["bear.operating","bear.policy"]
    spec, state, head = x.service._load(child)
    assert state["status"] == "SUCCEEDED", state
    assert [".".join(call) for call in x.provider.calls] == list(cont.native.STAGE_ORDER)[2:]
    assert state["provider_requests"] == len(state["reservations"]) == 7 and state["new_llm_calls"] == 0
    assert all(row["status"] == "SETTLED" for row in state["reservations"].values())
    assert state["responses"]["bear.policy"]["sha256"] == x.receipt["correction_response_sha256"]
    assert x.service._bound(state["responses"]["bear.terminal"])["request_sha256"] == x.receipt["next_request_sha256"]
    assert spec[cont.MARKER]["original_request_sha256"] != spec[cont.MARKER]["correction_request_sha256"]
    assert cont.Decimal(spec["ancestor_spend"]) == cont.Decimal(x.state["settled_cost"]) + cont.Decimal("0.001")
    repeated = client.post(url, json=body)
    assert repeated.json()["status"] == "SUCCEEDED" and repeated.json()["task_id"] == child
    assert len(x.provider.calls) == 7 and x.service._load(child)[2] == head
    assert x.service._load(x.parent_id)[2] == x.head
    assert not completion.valuation_receipt_path(root, child).exists()  # TEST_ONLY cannot publish a live valuation.


def test_terminal_failure_stops_without_base_or_duplicate_charge(prefix):
    x = prefix
    x.provider.fail_at = 1
    child = x.service.continue_policy(x.parent_id, x.pin, x.binding)["task_id"]
    failed = x.service.run(child)
    assert failed["status"] == "FAILED" and failed["error_code"].startswith("BEAR_TERMINAL_")
    assert set(failed["responses"]) == cont.ANNUAL
    assert x.service.continue_policy(x.parent_id, x.pin, x.binding)["status"] == "FAILED"
    assert x.provider.calls == [("bear","terminal")]


def test_altered_outer_response_bytes_never_dispatch(prefix):
    x = prefix
    flags = {"financing_policy_correction_source_sha256": x.receipt["original_response"]["sha256"]}
    assert cont.history_fields(x.service, x.parent_id, x.head, flags)["financing_policy_terminal_continuation_available"]
    child = x.service.continue_policy(x.parent_id, x.pin, x.binding)["task_id"]
    path = x.folder / "response.json"
    path.write_bytes(b'{"response":{"text":"ignored duplicate"},' + path.read_bytes()[1:])
    assert not cont.history_fields(x.service, x.parent_id, x.head, flags)["financing_policy_terminal_continuation_available"]
    with pytest.raises(ValueError, match="hash mismatch"):
        x.service.run(child)
    assert not x.provider.calls


def test_interim_cash_repetition_uses_original_observation_dates():
    ctx = {k: dict(year=2026, minimum_cny=amount, observed_through="2026-09-30") for k, amount in (
        ("annual_capex_floor","14.10"), ("annual_investment_receipts_floor","49.87"))}
    series = {k: dict(values=[v]*10) for k, v in (("maintenance_capex","14.10"), ("growth_capex","0.00"),
                                                  ("investment_cash_received","49.87"))}
    assert [(r["field"],r["annual_cny"],r["observed_through"],r["through_year"]) for r in
            cont._limitations(dict(years=list(range(2026,2036)),series=series),ctx)] == [
                ("investment_cash_received","49.87","2026-09-30",2035),("total_capex","14.10","2026-09-30",2035)]


def test_versioned_publication_cold_match_and_mismatch(sealed_case, monkeypatch):
    inputs, service, state = sealed_case
    spec, _, _ = service._load(TASK)
    spec.pop("gross_capex_plan_binding")
    spec[cont.MARKER] = dict(annual_input_limitations=[{"classification":"RECURRENCE_UNVERIFIED"}])
    monkeypatch.setattr(publication, "ContinuationService", lambda _: service)
    adapter = publication.legacy.adapter.run_direct_owner_cash_research
    def evaluate(*args, **kw):
        outcome, descriptor = adapter(*args, **kw)
        return outcome, SimpleNamespace(as_policy=descriptor.as_policy, input_sha256="private")
    monkeypatch.setattr(publication.legacy.adapter, "run_direct_owner_cash_research", evaluate)
    root = inputs["root"]
    completion.run_and_seal_parent_cash_task(service, TASK)
    path = completion.valuation_receipt_path(root, TASK)
    pin = dict(path=path.relative_to(root).as_posix(),sha256=cont.native._hash(path.read_bytes()))
    assert json.loads(path.read_bytes())["schema_version"] == publication.RECEIPT_SCHEMA
    result = publication.replay(root=root, receipt_binding=pin, now=inputs["now"])
    assert result["provenance"]["task_record_binding"] == HEAD and result["adoptable_valuation"] is False
    assert result["annual_input_limitations"] == spec[cont.MARKER]["annual_input_limitations"]
    assert all(s["annual_rows"][0]["scheduled_owner_distribution_cny"] == "10" for s in
               result["valuation"]["assumptions"]["scenario_calculations"].values())
    completion.seal_completed_parent_cash_task(service, TASK)
    state["responses"].pop("bear.terminal")
    with pytest.raises(ValueError, match="PARENT_TASK_EXACT_LIVE_SUCCESS_REQUIRED"):
        publication.replay(root=root, receipt_binding=pin, now=inputs["now"])
