"""Isolated IPS lifecycle, authenticating adapters and ledger-risk continuity."""
from datetime import datetime
import hashlib
import json

import pytest

from value_investment_agent.application.portfolio.private_portfolio_service import (
    PrivateJournal, PrivatePortfolioService, JournalValidationError, JournalConflict,
)
from value_investment_agent.application.portfolio import private_risk_projection as projection

NOW = datetime.fromisoformat("2026-10-14T20:00:00+08:00")


def full_policy():
    return {"investable_assets_cny": "10000", "core_value_budget_cny": "7000",
        "hotspot_budget_cny": "2000", "cash_reserve_cny": "1000", "minimum_cash_cny": "1000",
        "max_single_security_pct": "80", "max_single_industry_pct": "90", "max_factor_pct": "100",
        "hotspot_single_trade_risk_pct": "1", "max_drawdown_pct": "20",
        "financing_allowed": False, "risk_tools_allowed": False, "dividend_income_goal_cny": "500",
        "effective_date": "2026-10-12", "time_horizon_years": "5", "risk_tolerance": "BALANCED",
        "concentration_allowed": True,
        "sleeves": {"CORE_VALUE": {"cash_cny": "5000", "risk_budget_cny": "1400"},
            "HOTSPOT_SATELLITE": {"cash_cny": "2000", "risk_budget_cny": "400", "single_security_risk_cny": "100"}}}


@pytest.fixture
def service(tmp_path):
    service = PrivatePortfolioService(PrivateJournal(tmp_path / "TEST_ONLY-journal.jsonl"))
    service.initialize({"idempotency_key": "init", "expected_revision": 0, "account_scope": "TEST_ONLY_IPS",
        "as_of": "2026-10-10", "cash_cny": "8000", "holdings": [{"symbol": "300364", "exchange": "SZSE",
            "quantity": "100", "cost_basis_cny": "2000"}], "sleeve_allocations": {"300364": {"CORE_VALUE": "100"}},
        "policy": {}, "confirmed_at": "2026-10-10T20:00:00+08:00", "confirmation_note": "TEST ONLY"})
    return service


def prepare(service, policy):
    return service.prepare_policy({"idempotency_key": f"policy-{len(service.records())}",
        "expected_revision": len(service.records()), "policy": policy})


def confirm_request(service, digest):
    return {"idempotency_key": f"confirm-{len(service.records())}", "expected_revision": len(service.records()),
        "prepared_record_sha256": digest, "confirmed_at": "2026-10-12T20:00:00+08:00",
        "confirmation_note": "TEST ONLY explicit IPS confirmation"}


def confirm_policy(service, policy=None):
    _, digest = prepare(service, policy or full_policy())
    return service.confirm_policy(confirm_request(service, digest))


def quotes(monkeypatch, *, price="30", stale=False):
    from value_investment_agent.application.product import quote_bridge
    monkeypatch.setattr(quote_bridge, "execute_quote_bridge_for_symbol", lambda *args, **kwargs: {
        "compatibility": {"verified_quote": {"eligible": True}}, "quote": {
            "display_price": price, "quote_date": "2026-10-13" if stale else "2026-10-14",
            "latest_completed_session": "2026-10-14", "bundle_sha256": "a" * 64}})


def attributes(root, policy):
    runtime = root / "runtime"
    runtime.mkdir(exist_ok=True)
    source = runtime / "TEST_ONLY-source.json"
    source.write_text(json.dumps({"test_fixture": True}), encoding="utf-8")
    artifact = {"schema_version": "security-risk-attributes-evidence-v1", "namespace": "PUBLIC_RESEARCH",
        "action": "no_order", "available_at": "2026-10-12T18:00:00+08:00", "valid_until": "2026-10-15T18:00:00+08:00",
        "source_bindings": [{"path": "runtime/TEST_ONLY-source.json", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
        "attributes": {"symbol": "300364", "industry": "TEST_FIXTURE_ONLY", "cyclical": False,
            "liquidity_profile": "LIQUID", "common_factors": ["TEST_FACTOR"], "evidence_refs": [{"id": "TEST_ONLY"}]}}
    target = runtime / "TEST_ONLY-attributes.json"
    target.write_text(json.dumps(artifact), encoding="utf-8")
    policy["security_attribute_bindings"] = {"300364": {"path": "runtime/TEST_ONLY-attributes.json",
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}}
    return source


def test_partial_draft_does_not_activate_policy_and_cannot_confirm(service):
    before = service.portfolio_view()
    draft, digest = prepare(service, {"investable_assets_cny": "10000"})
    assert "effective_date" in draft["missing_fields"]
    assert service.policy_view()["status"] == "NOT_CONFIRMED"
    assert service.policy_view()["pending_policy"]["prepared_record_sha256"] == digest
    with pytest.raises(JournalValidationError, match="Missing confirmed IPS"):
        service.confirm_policy(confirm_request(service, digest))
    assert service.portfolio_view()["positions"] == before["positions"]
    assert service.portfolio_view()["cash_cny"] == before["cash_cny"]


def test_policy_confirmation_idempotence_and_unknown_fields(service):
    _, digest = prepare(service, full_policy())
    request = confirm_request(service, digest)
    first = service.confirm_policy(request)
    assert service.confirm_policy(request) == first
    view = PrivatePortfolioService(service.journal).policy_view()
    assert view["status"] == "CONFIRMED" and view["missing_fields"] == []
    assert all(not record["changes_holdings"] for record in service.records()[1:])
    with pytest.raises(JournalValidationError, match="unknown policy"):
        prepare(service, {"target_weight": "80"})
    with pytest.raises(JournalConflict):
        service.confirm_policy({**request, "idempotency_key": "other"})


@pytest.mark.parametrize("change", [
    {"core_value_budget_cny": "9500"}, {"financing_allowed": "false"},
    {"max_single_security_pct": "101"}, {"cash_reserve_cny": "500"},
    {"investable_assets_cny": "NaN"}, {"effective_date": "bad"},
])
def test_invalid_draft_rejected_without_write(service, change):
    with pytest.raises(JournalValidationError):
        prepare(service, {**full_policy(), **change})
    assert len(service.records()) == 1


def test_cash_partition_conflict_and_future_policy_fail_closed(service):
    policy = full_policy()
    policy["sleeves"]["CORE_VALUE"]["cash_cny"] = "5001"
    _, digest = prepare(service, policy)
    with pytest.raises(JournalValidationError, match="exactly partition"):
        service.confirm_policy(confirm_request(service, digest))
    policy = full_policy()
    policy["effective_date"] = "2026-10-15"
    confirm_policy(service, policy)
    result = projection.review_private_risk_rehearsal(service.journal, generated_at=NOW)
    assert "POLICY_NOT_EFFECTIVE" in result["blockers"]
    assert result["engine"]["position_guidance"] is None


def test_no_quotes_keeps_ledger_facts_visible(service):
    confirm_policy(service)
    result = projection.review_private_risk_rehearsal(service.journal, generated_at=NOW)
    assert result["facts"]["cash_cny"] == "8000"
    assert result["facts"]["cost_basis_total_cny"] == "2000"
    assert result["facts"]["total_equity_cny"] is None
    assert result["facts"]["positions"][0]["unrealized_pnl_cny"] is None
    payload = projection.build_risk_input(service._replay(service.records()), sellable_as_of=NOW.date())
    assert payload["shared_budget"]["core_value_budget"] == "0.7"
    assert payload["sleeves"]["HOTSPOT_SATELLITE"]["cash_cny"] == "2000"
    assert payload["cash_reserve_cny"] == "1000"
    assert payload["security_attributes"] is None


@pytest.mark.parametrize("invalid", ["not-a-number", "NaN"])
def test_invalid_quote_keeps_facts_and_policy_evidence(service, tmp_path, monkeypatch, invalid):
    quotes(monkeypatch, price=invalid)
    confirm_policy(service)
    result = projection.review_private_risk_rehearsal(service.journal, generated_at=NOW, repository_root=tmp_path)
    assert result["facts"]["cash_cny"] == "8000"
    assert result["facts"]["total_equity_cny"] is None
    replayed = service._replay(service.records())
    payload = projection.build_risk_input(replayed, sellable_as_of=NOW.date())
    assert payload["portfolio"]["policy"]["evidence_refs"][0]["id"] == replayed.policy["_record_sha256"]


def test_verified_quotes_mark_equity_but_do_not_invent_attributes(service, tmp_path, monkeypatch):
    quotes(monkeypatch)
    confirm_policy(service)
    result = projection.review_private_risk_rehearsal(service.journal, generated_at=NOW, repository_root=tmp_path)
    assert result["facts"]["total_equity_cny"] == "11000"
    assert result["facts"]["unrealized_pnl_total_cny"] == "1000"
    assert result["facts"]["current_drawdown_pct"] is None
    assert result["engine"]["trade_eligible"] is False
    view = service.portfolio_view(repository_root=tmp_path, generated_at=NOW)
    assert view["total_equity_cny"] == "11000"
    assert view["positions"][0]["floating_pnl_cny"] == "1000"
    quotes(monkeypatch, stale=True)
    assert service.portfolio_view(repository_root=tmp_path, generated_at=NOW)["total_equity_cny"] is None


def test_multi_lot_costs_and_unregistered_fixture_attributes_remain_blocked(service, tmp_path, monkeypatch):
    quotes(monkeypatch)
    policy = full_policy()
    source = attributes(tmp_path, policy)
    confirm_policy(service, policy)
    request = {"idempotency_key": "buy", "expected_revision": len(service.records()), "fill": {
        "transaction_id": "TEST_ONLY-buy", "side": "BUY", "sleeve": "CORE_VALUE", "symbol": "300364",
        "exchange": "SZSE", "quantity": "100", "price_cny": "30", "fees_cny": "5",
        "trade_date": "2026-10-13", "next_sell_session": "2026-10-14", "trading_unit": "100"}}
    _, digest = service.prepare_fill(request)
    service.confirm_fill({"idempotency_key": "confirm-buy", "expected_revision": len(service.records()),
        "prepared_record_sha256": digest, "confirmed_at": "2026-10-13T21:00:00+08:00", "confirmation_note": "TEST ONLY"})
    service.reconcile({"idempotency_key": "reconcile", "expected_revision": len(service.records()),
        "reconciled_at": "2026-10-13T21:05:00+08:00", "confirmation_note": "TEST ONLY"})
    result = projection.review_private_risk_rehearsal(service.journal, generated_at=NOW, repository_root=tmp_path)
    assert result["engine"]["status"] == "BLOCKED_PRIVATE_INPUT"
    assert "security_attributes.missing" in result["blockers"]
    payload = projection.build_risk_input(service._replay(service.records()), sellable_as_of=NOW.date(),
        repository_root=tmp_path, generated_at=NOW)
    core = payload["sleeves"]["CORE_VALUE"]
    assert core["cash_cny"] == "1995"
    assert len(payload["allocations"]) == 1
    assert payload["allocations"][0]["cost_basis_cny"] == "5005"
    assert core["capital_budget_cny"] == "7000"
    assert payload["security_attributes"] is None
    assert result["facts"]["total_equity_cny"] == "10995"
    source.write_text("tampered", encoding="utf-8")
    result = projection.review_private_risk_rehearsal(service.journal, generated_at=NOW, repository_root=tmp_path)
    assert "security_attributes.missing" in result["blockers"]
    assert result["facts"]["total_equity_cny"] == "10995"


def test_authenticated_policy_and_marked_portfolio_routes(service, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api import private_routes
    from value_investment_agent.presentation.web_api.local_auth import LocalOperatorSession
    secret = "TEST_ONLY-bootstrap-" + "0" * 40
    monkeypatch.setattr(private_routes, "resolve_private_root", lambda **kwargs: service.journal.path)
    app = FastAPI()
    private_routes.register_private_routes(app, tmp_path, sessions=LocalOperatorSession(bootstrap_secret=secret), port=8001)
    with TestClient(app, base_url="http://127.0.0.1:8001", client=("127.0.0.1", 51000)) as client:
        client.headers["origin"] = "http://127.0.0.1:8001"
        assert client.get("/api/v1/private/portfolio/policy").status_code == 401
        assert client.post("/api/v1/private/portfolio/policy/prepare", json={}).status_code == 401
        token = client.post("/api/v1/private/session/unlock", json={"bootstrap_token": secret}).json()["token"]
        client.headers["x-local-session"] = token
        prepared = client.post("/api/v1/private/portfolio/policy/prepare", json={
            "idempotency_key": "api-policy", "expected_revision": 1, "policy": full_policy()})
        assert prepared.status_code == 200, prepared.text
        body = prepared.json()
        confirmed = client.post("/api/v1/private/portfolio/policy/confirm", json={
            "idempotency_key": "api-confirm", "expected_revision": 2, "prepared_record_sha256": body["record_sha256"],
            "confirmed_at": "2026-10-12T20:00:00+08:00", "confirmation_note": "TEST ONLY"})
        assert confirmed.status_code == 200, confirmed.text
        assert client.get("/api/v1/private/portfolio/policy").json()["status"] == "CONFIRMED"
        quotes(monkeypatch)
        # No account resolver outside this injected isolated journal is called.
        assert client.get("/api/v1/portfolio").json()["total_equity_cny"] == "11000"
        risk = client.get("/api/v1/private/portfolio/risk").json()
        assert risk["facts"]["total_equity_cny"] == "11000"
        assert "security_attributes.missing" in risk["blockers"]


def test_cash_only_authenticated_initialize_ips_and_first_buy(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api import private_routes
    from value_investment_agent.presentation.web_api.local_auth import LocalOperatorSession
    service = PrivatePortfolioService(PrivateJournal(tmp_path / "TEST_ONLY-cash-journal.jsonl"))
    request = {"idempotency_key": "cash-init", "expected_revision": 0, "account_scope": "TEST_ONLY_CASH",
        "as_of": "2026-10-10", "cash_cny": "8000", "holdings": [], "sleeve_allocations": {},
        "policy": {}, "confirmed_at": "2026-10-10T20:00:00+08:00", "confirmation_note": "TEST ONLY cash-only account"}
    secret = "TEST_ONLY-bootstrap-" + "1" * 40
    monkeypatch.setattr(private_routes, "resolve_private_root", lambda **kwargs: service.journal.path)
    app = FastAPI()
    private_routes.register_private_routes(app, tmp_path, sessions=LocalOperatorSession(bootstrap_secret=secret), port=8001)
    with TestClient(app, base_url="http://127.0.0.1:8001", client=("127.0.0.1", 51000)) as client:
        client.headers["origin"] = "http://127.0.0.1:8001"
        token = client.post("/api/v1/private/session/unlock", json={"bootstrap_token": secret}).json()["token"]
        client.headers["x-local-session"] = token
        missing = dict(request)
        del missing["holdings"]
        assert client.post("/api/v1/private/portfolio/initialize", json=missing).status_code == 422
        assert service.records() == []
        first = client.post("/api/v1/private/portfolio/initialize", json=request)
        assert first.status_code == 200, first.text
        assert client.post("/api/v1/private/portfolio/initialize", json=request).json() == first.json()
        view = client.get("/api/v1/portfolio").json()
        assert view["status"] == "CONNECTED" and view["positions"] == []
        assert view["cash_cny"] == view["total_equity_cny"] == "8000"
        assert view["valuation"]["status"] == "CASH_ONLY_NO_QUOTE_REQUIRED"
        confirm_policy(service)
        risk = client.get("/api/v1/private/portfolio/risk").json()
        assert risk["status"] != "NOT_CONNECTED"
        assert risk["facts"]["positions"] == [] and risk["facts"]["total_equity_cny"] == "8000"
        assert risk["facts"]["market_value_total_cny"] == risk["facts"]["unrealized_pnl_total_cny"] == "0"
        assert "security_attributes.missing" not in risk["blockers"]
    reloaded = PrivatePortfolioService(service.journal)
    assert reloaded.portfolio_view()["status"] == "CONNECTED"
    assert reloaded._replay(reloaded.records()).state.lots == ()
    _, digest = reloaded.prepare_fill({"idempotency_key": "first-buy", "expected_revision": len(reloaded.records()),
        "fill": {"transaction_id": "TEST_ONLY-first-buy", "side": "BUY", "sleeve": "CORE_VALUE", "symbol": "300364",
            "exchange": "SZSE", "quantity": "100", "price_cny": "20", "fees_cny": "5",
            "trade_date": "2026-10-13", "next_sell_session": "2026-10-14", "trading_unit": "100"}})
    reloaded.confirm_fill({"idempotency_key": "confirm-first-buy", "expected_revision": len(reloaded.records()),
        "prepared_record_sha256": digest, "confirmed_at": "2026-10-13T21:00:00+08:00", "confirmation_note": "TEST ONLY"})
    assert reloaded.portfolio_view()["cash_cny"] == "5995"
    assert reloaded.portfolio_view()["positions"][0]["quantity"] == "100"
