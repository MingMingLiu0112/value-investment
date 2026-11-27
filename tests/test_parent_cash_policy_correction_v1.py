"""One paid-format intent, offline provider, real shared reservation/settlement and append-only receipt."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from value_investment_agent.application.product.common import _native_path
from value_investment_agent.application.research import parent_cash_policy_correction_v1 as correction
from value_investment_agent.application.research import parent_cash_task_completion_v1 as completion
from value_investment_agent.infrastructure.agent_runtime.provider import LLMRequest, LLMResponse
from value_investment_agent.presentation.web_api import parent_cash_history_routes as routes

NOW = datetime(2026, 11, 27, tzinfo=timezone.utc)
TASK = "rt-" + "3" * 32
YEARS = list(range(2026, 2036))
FIELDS = ("cash_floor", "commitments_outside_capex", "growth_capex", "investment_cash_received",
          "maintenance_capex", "other_mandatory_cash", "parent_profit", "payout_ratio", "reserve_ratio")


class Provider:
    def __init__(self):
        self.calls = []
        self.change = lambda reply: None
        self.timeout = False

    def complete(self, request):
        self.calls.append(request)
        if self.timeout:
            raise TimeoutError()
        raw = json.loads(json.loads(request.user)["original_response_text"])
        reply = {k: raw[k] for k in ("years", "series")}
        self.change(reply)
        return LLMResponse(json.dumps(reply), 120, 200, "deepseek-flash")


@pytest.fixture
def case(tmp_path, monkeypatch):
    root = Path(_native_path(tmp_path))
    provider = Provider()
    svc = correction.native.ParentCashTaskServiceV3(root, test_provider=provider)
    directory = svc._directory(TASK)
    directory.mkdir(parents=True)
    def bind(path, value):
        correction._put(path, value)
        return svc._binding(path)
    cfg = dict(model_id="deepseek-flash", max_run_cost="1", daily_cost_limit="2",
               input_cost_per_million="2", output_cost_per_million="8", max_completion_tokens_cap=8192)
    spec = dict(task_id=TASK, mode="TEST_ONLY_PARENT_CASH_V3", created_at=NOW.isoformat(),
                source_fingerprint="f" * 64, conditional_financing_stress={"residual_stress_rate": "0.03"},
                mandatory_cash_classification="DISJOINT_V1", bear_operating_wire="MATCHED_QUARTER_V2",
                config=cfg, ancestor_spend="0.15", spec_binding=bind(root / "runtime/spec.json", dict(symbol="600887",
                action="no_order")))
    term = dict(values=["1.00"] * 10, evidence_anchors=["cash"], mechanism="Annual mechanism",
                counter_evidence="Scope uncertain", reopen_condition="Reopen on filing")
    series = {k: deepcopy(term) for k in FIELDS}
    series["other_mandatory_cash"]["cash_class_by_year"] = ["NON_FINANCING"] * 10
    raw = dict(years=YEARS, series=series, terminal_policy={"cash": "Conditional, unapproved"},
               reopen_conditions="A verified repayment schedule")
    wire = LLMRequest("policy", "original economic request", json.dumps(dict(required_fields=FIELDS,
                      required_years=YEARS)), {}, 8192, "Return the annual fields")
    charges, pins = {}, {}
    for key, stage in (("a"*64, "bear.operating"), ("b"*64, "bear.policy")):
        response = LLMResponse(json.dumps(raw) if stage == "bear.policy" else "{}", 100, 100, cfg["model_id"])
        pins[stage] = bind(directory / f"response-{key}.json", dict(scenario=stage, action="no_order",
            source_fingerprint=spec["source_fingerprint"], request_sha256=correction._digest(vars(wire)),
            response=vars(response)))
        cost = correction.Accounting._cost(100, 100, cfg)
        day = NOW.date().isoformat()
        svc.daily._daily_budget(day, key, cost, cfg)
        svc.daily._daily_budget(day, key, cost, cfg, settle=True)
        charges[key] = dict(status="SETTLED", scenario=stage, day=day, cost=str(cost), actual_cost=str(cost))
    state = dict(status="FAILED", error_code=correction.ERROR, updated_at=NOW.isoformat(), input_sha256="4"*64,
                 reservations=charges, reserved_cost="0", settled_cost="0.002",
                 responses={"bear.operating": pins["bear.operating"]}, returned_responses=list(pins.values()))
    head = bind(directory / "head.json", state)
    (directory / "input.json").write_text("{}", encoding="utf8")
    monkeypatch.setattr(svc, "_load", lambda task_id: (spec, state, head) if task_id == TASK else pytest.fail(task_id))
    monkeypatch.setattr(svc, "_implementation_matches", lambda _: True)
    monkeypatch.setattr(svc, "_context", lambda *_: dict(input_fingerprint=spec["source_fingerprint"]))
    monkeypatch.setattr(svc, "_stage_outputs", lambda *a, **kw: {"bear": {"operating": {"years": YEARS}}})
    monkeypatch.setattr(svc, "_wire", lambda spec, stage, request, **kw: request)
    monkeypatch.setattr(correction, "_stage_request", lambda service, spec, context, stage, prior:
        wire if stage == "policy" else LLMRequest("terminal", "terminal", json.dumps(prior), {}))
    def parse(spec, stage, response, **kwargs):
        assert kwargs["request"] == wire and kwargs["source_fingerprint"] == spec["source_fingerprint"]
        result = json.loads(response.text)
        if "terminal_policy" in result:
            raise ValueError("PARENT_V3_FINANCING_WIRE_RESPONSE_INVALID")
        return result
    monkeypatch.setattr(svc, "_parse_stage", parse)
    monkeypatch.setattr(correction.native, "preflight_annual_cash_upper_bound_v3", lambda **kwargs: None)
    binding = lambda *args: spec["spec_binding"]
    monkeypatch.setattr(completion, "registered_cash_task_spec", binding)
    monkeypatch.setattr(routes, "registered_cash_task_spec", binding)
    monkeypatch.setattr(routes, "ParentCashTaskServiceV3", lambda _: svc)
    monkeypatch.setattr(routes, "resolve_research_task_root", lambda project: root)
    monkeypatch.setattr(svc, "read", lambda task_id: dict(state, spec_binding=spec["spec_binding"]))
    monkeypatch.setattr(routes, "authorize", lambda *args, **kwargs: None)
    app = FastAPI()
    routes.register_parent_cash_history_routes(app, project=root, sessions=None, port=8001)
    digest = pins["bear.policy"]["sha256"]
    return SimpleNamespace(svc=svc, spec=spec, state=state, provider=provider, raw=raw, digest=digest,
        folder=correction._folder(svc, TASK), client=TestClient(app),
        run=lambda create: correction.correct_or_read(svc, TASK, digest, create=create, now=NOW))


def test_company_post_replay_and_frozen_parent(case):
    c = case
    prefix = "/api/v1/operating-research/parent-cash-tasks"
    get = prefix + f"/v3/{TASK}/bear-policy-correction-v1/{c.digest}"
    history = lambda: c.client.get(prefix + "/history?symbol=600887").json()["items"][0]
    assert history()["financing_policy_correction_available"] is True
    assert c.client.get(get).json()["status"] == "CORRECTION_NOT_STARTED"
    assert c.client.get(get[:-64] + "d"*64).status_code == 422
    assert not c.folder.exists() and not c.provider.calls
    body = dict(symbol="600887", continue_from_task_id=TASK)
    before = deepcopy(c.state)
    response = c.client.post(prefix + "/by-company", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "CORRECTION_VERIFIED" and result["paid_task_status"] == "FAILED"
    assert result["original_response"]["sha256"] == c.digest and result["stage"] == "bear.policy"
    assert result["original_request_sha256"] != result["correction_request_sha256"]
    assert result["correction_request_sha256"] == correction._digest(vars(c.provider.calls[0]))
    assert result["research_notes"] == {k: c.raw[k] for k in correction.EXTRAS}
    assert c.client.get(get).json() == c.client.post(prefix + "/by-company", json=body).json() == result
    assert history()["financing_policy_correction_available"] is False
    drafts, request = correction.replay_for_terminal(c.svc, TASK, c.digest, result["receipt_sha256"])
    assert drafts["policy"] == {k: c.raw[k] for k in ("years","series")}
    assert request.role == "terminal" and correction._digest(vars(request)) == result["next_request_sha256"]
    assert len(c.provider.calls) == 1 and c.state == before
    assert result["settled_cost_cny"] == "0.00184" and result["formal_eligibility"] is False


@pytest.mark.parametrize("field", ["values", "evidence_anchors", "mechanism", "counter_evidence", "reopen_condition",
                                   "cash_class_by_year", "years", "extra"])
def test_any_annual_change_seals_a_rejection(case, field):
    def change(reply):
        if field == "years":
            reply["years"][0] = float(reply["years"][0])
        elif field == "extra":
            reply["reopen_conditions"] = "Extra commentary"
        else:
            reply["series"]["other_mandatory_cash"][field] = ["different"]
    case.provider.change = change
    rejected = case.run(True)
    assert rejected["status"] == "CORRECTION_REJECTED" and rejected["reason"] == "CORRECTION_ANNUAL_CONTENT_CHANGED"
    assert case.run(True) == case.run(False) == rejected
    with pytest.raises(ValueError, match="CORRECTION_NOT_ADMITTED"):
        correction.replay_for_terminal(case.svc, TASK, case.digest, rejected["receipt_sha256"])
    assert len(case.provider.calls) == 1


def test_economic_gate_and_pinned_receipt(case, monkeypatch):
    def reject(**kwargs):
        raise ValueError("DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2027")
    monkeypatch.setattr(correction.native, "preflight_annual_cash_upper_bound_v3", reject)
    result = case.run(True)
    assert result["reason"] == "DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2027" and "next_stage" not in result
    with pytest.raises(ValueError, match="CORRECTION_RECEIPT_PIN_CHANGED"):
        correction.replay_for_terminal(case.svc, TASK, case.digest, "0"*64)


def test_ambiguous_call_never_resends(case):
    case.provider.timeout = True
    assert case.run(True)["status"] == case.run(True)["status"] == "CORRECTION_OUTCOME_UNKNOWN"
    assert len(case.provider.calls) == 1 and not (case.folder / "receipt.json").exists()


def test_recover_retained_response_after_settlement_interruption(case, monkeypatch):
    settle = case.svc.daily._daily_budget
    def interrupted(*args, **kwargs):
        if kwargs.get("settle"):
            raise OSError("interrupted")
        return settle(*args, **kwargs)
    monkeypatch.setattr(case.svc.daily, "_daily_budget", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        case.run(True)
    assert (case.folder / "response.json").exists() and not (case.folder / "receipt.json").exists()
    monkeypatch.setattr(case.svc.daily, "_daily_budget", settle)
    assert case.run(True)["status"] == "CORRECTION_VERIFIED" and len(case.provider.calls) == 1


def test_budget_refused_and_tampered_original(case):
    case.spec["ancestor_spend"] = "1"
    with pytest.raises(ValueError, match="CORRECTION_LINEAGE_BUDGET_EXHAUSTED"):
        case.run(True)
    assert not case.provider.calls
    case.spec["ancestor_spend"] = "0"
    (case.svc.root / case.state["returned_responses"][-1]["path"]).write_bytes(b"{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        case.run(True)
    assert not case.provider.calls


@pytest.mark.parametrize("name", ["intent", "dispatch", "response", "receipt"])
def test_replay_fails_closed_on_tampered_records(case, name):
    result = case.run(True)
    path = case.folder / f"{name}.json"
    changed = json.loads(path.read_bytes())
    changed["unbound"] = True
    path.write_bytes(correction._bytes(changed))
    with pytest.raises(ValueError):
        correction.replay_for_terminal(case.svc, TASK, case.digest, result["receipt_sha256"])
    assert len(case.provider.calls) == 1
