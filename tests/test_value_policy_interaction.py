"""Synthetic user confirmation only; all writes stay in pytest's repository .tmp."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from test_value_policy_review import review_fixture
from test_value_price_policy import NOW
from value_investment_agent.application.decision import value_price_policy as contract
from value_investment_agent.application.decision.value_policy_interaction import (
    PERMISSION, PolicyAccessDenied, PolicyConflict, PolicyPrincipal, ValuePolicyInteractionService,
)
from value_investment_agent.presentation.web_api.local_auth import LocalOperatorSession
from value_investment_agent.presentation.web_api.value_policy_routes import register_value_policy_routes

ACTOR = PolicyPrincipal("synthetic-owner", frozenset({PERMISSION}))
CONFIRM = dict(acknowledged=True, note="Synthetic explicit owner confirmation")


def setup(tmp_path, monkeypatch):
    plan, source, docs, manifest, manifest_path = review_fixture(tmp_path, monkeypatch)
    explanation = dict(symbol="600887", action="no_order", research_as_of="2026-10-11",
        decision_as_of="2026-10-14", research_version=plan["research_version"],
        candidate_action="BUY_CANDIDATE", model_id=plan["model_id"],
        valuation=dict(symbol="600887", valuation_date="2026-10-11", model_version=plan["model_version"],
            model_type=plan["model_type"], bear_value="10", base_value="12", bull_value="14", status="conditional_research_only"),
        model_validity=dict(status="VALID", model_id=plan["model_id"], last_material_event_check="2026-10-14"),
        price_context=dict(positive_price_review_eligible=False,
            price_attractiveness=dict(profile_id=plan["profile_id"]),
            price_bridge=dict(symbol="600887", bridge_status="READY", current_price="9",
                quote_date="2026-10-14", quote_status="verified_close")),
        blockers=["G3_PENDING"])
    path = tmp_path / "runtime/600887-value-decision-explanation.json"
    raw = json.dumps(explanation).encode()
    path.write_bytes(raw)
    plan["source_bindings"].append(dict(path=path.relative_to(tmp_path).as_posix(), sha256=hashlib.sha256(raw).hexdigest()))
    plan.update(reference_close="9", market_trade_date="2026-10-14", current_quote_verified=True,
                price_comparison_eligible=False)
    service = ValuePolicyInteractionService(tmp_path,
        storage_relative=".tmp/value-policy-review/account-a", isolated=True)
    selection = dict(effective_from="2026-10-14", effective_through="2026-11-14",
        rationale="Synthetic owner choice", dividend_coverage_risk="Coverage unknown",
        rules=[dict(action="entry", scenario="bear", value_fraction="0.93", comparison="LTE",
                    rationale="Only review while thesis remains valid")])
    return service, selection, plan, source


def test_preview_confirmation_rebuilds_plan_without_g3_or_publication(tmp_path, monkeypatch):
    service, selection, plan, _ = setup(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    preview = service.preview("600887", selection, principal=ACTOR, now=NOW)
    assert preview["preparation"]["draft_prices"]["entry"] == "9.30"
    assert preview["preparation"]["existing_research_blockers"] == ["G3_PENDING"]
    result = service.confirm(preview["preview_id"], CONFIRM, principal=ACTOR, now=NOW)
    assert result["status"] == "REGISTERED"
    assert result["scope"] == "ISOLATED_TEST"
    assert result["conditional_plan"]["entry_trigger_price"] == "9.30"
    assert result["conditional_plan"]["entry_condition"]["triggered"] is None
    assert "G3_PENDING" in result["conditional_plan"]["blockers"]
    assert result["conditional_plan"]["formal_eligibility"] is False
    assert result["portfolio_eligibility"] is None
    assert result["production_published"] is result["research_approval_changed"] is False
    assert all(p.read_bytes() == content for p, content in before.items())
    assert not (tmp_path / "config").exists()
    restarted = ValuePolicyInteractionService(tmp_path,
        storage_relative=".tmp/value-policy-review/account-a", isolated=True)
    assert restarted.confirm(preview["preview_id"], CONFIRM, principal=ACTOR, now=NOW + timedelta(days=1)) == result
    status = restarted.status("600887", principal=ACTOR, now=NOW)
    assert status["status"] == "REGISTERED"
    assert status["conditional_plan"]["entry_trigger_price"] == "9.30"
    assert status["registered_policy"]["draft_prices"]["entry"] == "9.30"
    assert status["registered_policy"]["draft"]["rules"] == selection["rules"]
    assert restarted.status("600887", principal=PolicyPrincipal("other", ACTOR.permissions), now=NOW)["status"] == "NOT_REGISTERED"
    with pytest.raises(PolicyConflict):
        restarted.confirm(preview["preview_id"], {**CONFIRM, "note": "different"}, principal=ACTOR, now=NOW)


@pytest.mark.parametrize("fault", ["expiry", "basis", "source", "quote", "future_cutoff"])
def test_status_revalidates_latest_policy_and_never_uses_stale_plan(tmp_path, monkeypatch, fault):
    service, selection, plan, source = setup(tmp_path, monkeypatch)
    preview = service.preview("600887", selection, principal=ACTOR, now=NOW)
    service.confirm(preview["preview_id"], CONFIRM, principal=ACTOR, now=NOW)
    now = NOW
    if fault == "expiry":
        now += timedelta(days=40)
    elif fault == "basis":
        plan["model_version"] = "changed"
    elif fault == "source":
        source.write_bytes(b"changed")
    elif fault == "future_cutoff":
        now -= timedelta(minutes=1)
    else:
        plan["current_quote_verified"] = False
    status = service.status("600887", principal=ACTOR, now=now)
    if fault == "quote":
        assert status["status"] == "REGISTERED"
        assert status["conditional_plan"]["entry_trigger_price"] is None
        assert status["registered_policy"]["draft_prices"]["entry"] == "9.30"
    else:
        assert status["status"] == "REVIEW_REQUIRED"
        assert status["conditional_plan"] is None
    assert status["formal_eligibility"] is False


@pytest.mark.parametrize("fault", ["unauthorized", "another_actor", "expired", "source", "basis", "preview_tamper", "missing_ack", "missing_note", "extra_role", "revoked", "review"])
def test_confirmation_refuses_invalid_authority_or_changed_preview(tmp_path, monkeypatch, fault):
    service, selection, plan, source = setup(tmp_path, monkeypatch)
    principal, now, confirm = ACTOR, NOW, deepcopy(CONFIRM)
    preview = service.preview("600887", selection, principal=ACTOR, now=NOW)
    if fault in {"unauthorized", "revoked"}:
        principal = PolicyPrincipal(ACTOR.actor_id, frozenset())
    elif fault == "another_actor":
        principal = PolicyPrincipal("someone-else", ACTOR.permissions)
    elif fault == "expired":
        now += timedelta(minutes=31)
    elif fault == "source":
        source.write_bytes(b"changed")
    elif fault == "basis":
        plan["model_version"] = "new-model"
    elif fault == "preview_tamper":
        (service.store / (preview["preview_id"] + ".json")).write_text("{}", encoding="utf-8")
    elif fault == "missing_ack":
        confirm["acknowledged"] = False
    elif fault == "missing_note":
        confirm["note"] = " "
    elif fault == "extra_role":
        confirm["actor"] = "fake-authorized-actor"
    elif fault == "review":
        manifest = tmp_path / contract.REVIEW_MANIFEST_PATH
        manifest.write_bytes(b"changed")
    with pytest.raises((ValueError, PolicyAccessDenied)):
        service.confirm(preview["preview_id"], confirm, principal=principal, now=now)
    assert not list(service.store.glob("confirmed-*"))


def test_empty_rules_do_not_pick_default_and_cannot_register(tmp_path, monkeypatch):
    service, selection, _, _ = setup(tmp_path, monkeypatch)
    selection["rules"] = []
    preview = service.preview("600887", selection, principal=ACTOR, now=NOW)
    assert preview["status"] == "BLOCKED"
    assert all(v is None for v in preview["preparation"]["draft_prices"].values())
    with pytest.raises(ValueError):
        service.confirm(preview["preview_id"], CONFIRM, principal=ACTOR, now=NOW)


def test_parallel_double_confirmation_creates_one_commit(tmp_path, monkeypatch):
    service, selection, _, _ = setup(tmp_path, monkeypatch)
    preview = service.preview("600887", selection, principal=ACTOR, now=NOW)
    def confirm(_):
        svc = ValuePolicyInteractionService(tmp_path,
            storage_relative=".tmp/value-policy-review/account-a", isolated=True)
        return svc.confirm(preview["preview_id"], CONFIRM, principal=ACTOR, now=NOW)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(confirm, range(2)))
    assert results[0] == results[1]
    assert len(list(service.store.glob("confirmed-*"))) == 1


@pytest.mark.parametrize("path", ["config/policy", "runtime/private", "../escape", ".tmp/value-policy-review", "runtime/value-policy-review/real"])
def test_isolated_store_cannot_escape_test_scope(tmp_path, path):
    with pytest.raises(ValueError):
        ValuePolicyInteractionService(tmp_path, storage_relative=path, isolated=True)


def test_routes_reuse_sessions_permissions_and_factory_without_private_resolution(tmp_path, monkeypatch):
    service, selection, _, _ = setup(tmp_path, monkeypatch)
    api = FastAPI()
    session = LocalOperatorSession(bootstrap_secret="synthetic-only")
    token = session.unlock("synthetic-only")
    principal = [ACTOR]
    calls = []
    def factory():
        calls.append(True)
        return service
    register_value_policy_routes(api, get_service=factory, sessions=session,
        principal_resolver=lambda request: principal[0], clock=lambda: NOW)
    client = TestClient(api, base_url="http://127.0.0.1:8001", client=("127.0.0.1", 12345))
    path = "/api/v1/value-policy-review/600887/preview"
    assert client.post(path, json=selection).status_code == 401
    status_path = "/api/v1/value-policy-review/600887/status"
    assert client.get(status_path).status_code == 401
    assert client.get('/api/v1/value-policy-review/600887/handoff').status_code == 401
    assert calls == []
    headers = {"X-Local-Session": token}
    assert client.post(path, json=selection, headers={**headers, "origin": "https://evil.invalid"}).status_code == 403
    principal[0] = PolicyPrincipal("read-only", frozenset())
    assert client.post(path, json=selection, headers=headers).status_code == 403
    assert client.get(status_path, headers=headers).status_code == 403
    assert calls == []
    principal[0] = ACTOR
    response = client.post(path, json=selection, headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = dict(preview_id=response.json()["preview_id"], **CONFIRM)
    assert client.get(path).status_code == 405
    assert client.post("/api/v1/value-policy-review/000333/confirm", json=payload, headers=headers).status_code == 422
    response = client.post("/api/v1/value-policy-review/600887/confirm", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["conditional_plan"]["entry_trigger_price"] == "9.30"
    status = client.get(status_path, headers=headers)
    assert status.status_code == 200 and status.json()["status"] == "REGISTERED"
    assert status.headers["cache-control"] == "no-store"
    principal[0] = PolicyPrincipal("other-owner", ACTOR.permissions)
    assert client.get(status_path, headers=headers).json()["status"] == "NOT_REGISTERED"
    principal[0] = ACTOR
    assert client.post("/api/v1/value-policy-review/600887/confirm", json=payload, headers=headers).json() == response.json()
    session.invalidate()
    assert client.post(path, json=selection, headers=headers).status_code == 401
