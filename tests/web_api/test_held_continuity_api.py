"""Authenticated on-read continuity; isolated TEST_ONLY private journals."""
from datetime import datetime
import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from value_investment_agent.presentation.web_api import private_routes
from value_investment_agent.presentation.web_api.app import create_app
from value_investment_agent.application.portfolio import held_continuity as continuity
from value_investment_agent.application.portfolio.private_portfolio_service import PrivateJournal, PrivatePortfolioService

ROUTE = "/api/v1/private/portfolio/held-continuity"
NOW = datetime.fromisoformat("2026-10-16T20:00:00+08:00")


def client_for(root, journal, monkeypatch):
    monkeypatch.setattr(private_routes, "resolve_private_root", lambda **kwargs: journal)
    secret = "TEST_ONLY-bootstrap-" + "p" * 40
    client = TestClient(create_app(root, port=8791, bootstrap_secret=secret),
        base_url="http://127.0.0.1:8791", client=("127.0.0.1", 51000))
    client.headers.update({"host": "127.0.0.1:8791", "origin": "http://127.0.0.1:8791"})
    return client, secret


def unlock(client, secret):
    token = client.post("/api/v1/private/session/unlock", json={"bootstrap_token": secret}).json()["token"]
    client.headers["x-local-session"] = token


def initialize(path):
    service = PrivatePortfolioService(PrivateJournal(path))
    service.initialize({"idempotency_key": "init", "expected_revision": 0,
        "account_scope": "TEST_ONLY", "as_of": "2026-10-10", "cash_cny": "8000",
        "holdings": [{"symbol": "600887", "exchange": "SSE", "quantity": "100", "cost_basis_cny": "2000"}],
        "sleeve_allocations": {"600887": {"CORE_VALUE": "100"}}, "policy": {},
        "confirmed_at": "2026-10-10T20:00:00+08:00", "confirmation_note": "TEST_ONLY"})
    return service


def test_authentication_origin_and_disconnected_no_writes(tmp_path, monkeypatch):
    path = tmp_path / "TEST_ONLY.jsonl"
    client, secret = client_for(tmp_path, path, monkeypatch)
    assert client.get(ROUTE).status_code == 401
    unlock(client, secret)
    client.headers["origin"] = "http://example.invalid"
    assert client.get(ROUTE).status_code == 403
    client.headers["origin"] = "http://127.0.0.1:8791"
    response = client.get(ROUTE)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["revision"] == 0
    assert response.json()["status"] == "NOT_CONNECTED"
    assert not path.exists()


@pytest.mark.parametrize("signal,intent", [("BLOCKED", "WATCH"), ("CONDITION_PENDING", "EXIT")])
def test_real_route_revision_matches_portfolio_and_keeps_value_without_hotspot_timestamp(tmp_path, monkeypatch, signal, intent):
    path = tmp_path / "TEST_ONLY.jsonl"
    initialize(path)
    monkeypatch.setattr(continuity, "load_price_conditions", lambda *a, **k: {"items": []})
    value = {"symbol": "600887", "schema_version": "value-action-plan-v1", "action": "no_order",
        "action_intent": intent, "signal_state": signal, "blockers": ["TEST_ONLY_RESEARCH_GAP"],
        "exit_condition": {"status": "REVIEW_REQUIRED"}}
    monkeypatch.setattr(continuity, "load_registered_value_action_plans", lambda *a, **k: {"items": [value]})
    client, secret = client_for(tmp_path, path, monkeypatch)
    unlock(client, secret)
    before = path.read_bytes()
    result = client.get(ROUTE).json()
    assert result["schema_version"] == "private-held-continuity-v1"
    assert result["revision"] == client.get("/api/v1/portfolio").json()["revision"] == 1
    row = result["items"][0]
    assert row["strategy_plan"] == value
    assert "TEST_ONLY_RESEARCH_GAP" in row["data_gaps"]
    assert row["formal_eligibility"] is False
    assert ("INVALIDATION_OR_EXIT_REVIEW" in row["review_reasons"]) == (intent == "EXIT")
    assert path.read_bytes() == before


def snapshot(symbol, binding):
    payload = {"schema_version": "private-recording-time-judgment-snapshot-v1", "action": "no_order",
        "decision_id": "hotspot-" + symbol, "recorded_at": "2026-10-14T20:00:00+08:00",
        "plan": {"symbol": symbol, "action": "no_order", **binding}}
    payload["snapshot_sha256"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return payload


@pytest.mark.parametrize("mode", ["retained", "unavailable", "tampered", "current"])
def test_provider_uses_verified_current_then_private_confirmed_history_beyond_cap(tmp_path, monkeypatch, mode):
    symbol = "300364"
    binding = {"case_path": "runtime/TEST_ONLY-case.json", "case_sha256": "a" * 64}
    saved = snapshot(symbol, binding)
    if mode == "tampered":
        saved["plan"]["case_sha256"] = "b" * 64
    current = {"symbol": symbol, "action": "no_order", "signal_state": "WATCH"}
    monkeypatch.setattr(continuity, "load_price_conditions", lambda *a, **k: {"items":
        [{"symbol": symbol, "price_action_plan": current}] if mode == "current" else []})
    monkeypatch.setattr(continuity, "load_registered_value_action_plans", lambda *a, **k: {"items": []})
    calls = []
    def load(root, actual_symbol, actual_binding, *, now):
        calls.append(actual_symbol)
        assert actual_binding["case_sha256"] == binding["case_sha256"]
        if mode == "unavailable":
            raise ValueError("stale_quote")
        return {"symbol": actual_symbol, "action": "no_order", "source": "REVERIFIED_CASE"}
    monkeypatch.setattr(continuity, "load_held_price_plan", load)
    trades = [{"symbol": symbol, "judgment_snapshot": saved}]
    # Simulate many newer unrelated confirmed history entries; no retention cap.
    trades += [{"symbol": f"{i:06d}", "judgment_snapshot": None} for i in range(30)]
    _, provider = continuity.build_held_plan_provider(tmp_path, SimpleNamespace(trades=trades), now=NOW)
    result = provider(symbol)
    if mode == "current":
        assert result == current and calls == []
    elif mode == "retained":
        assert result["source"] == "REVERIFIED_CASE" and calls == [symbol]
    else:
        assert result is None
        assert calls == ([symbol] if mode == "unavailable" else [])


def test_route_replays_confirmed_snapshot_binding_without_public_registry_membership(tmp_path, monkeypatch):
    from value_investment_agent.application.portfolio import judgment_snapshot
    path = tmp_path / "TEST_ONLY-history.jsonl"
    service = initialize(path)
    binding = {"case_path": "runtime/TEST_ONLY-retained.json", "case_sha256": "a" * 64}
    monkeypatch.setattr(judgment_snapshot, "capture_judgment_snapshot",
        lambda root, fill: snapshot("600887", binding))
    _, digest = service.prepare_fill({"idempotency_key": "buy", "expected_revision": 1,
        "fill": {"transaction_id": "TEST_ONLY-buy", "side": "BUY", "sleeve": "HOTSPOT_SATELLITE",
            "symbol": "600887", "exchange": "SSE", "quantity": "100", "price_cny": "20",
            "fees_cny": "5", "trade_date": "2026-10-14", "next_sell_session": "2026-10-15",
            "trading_unit": "100", "decision_id": "hotspot-600887", "research_version": "TEST_ONLY"}},
        repository_root=tmp_path)
    service.confirm_fill({"idempotency_key": "confirm", "expected_revision": 2,
        "prepared_record_sha256": digest, "confirmed_at": "2026-10-14T21:00:00+08:00",
        "confirmation_note": "TEST_ONLY"})
    monkeypatch.setattr(continuity, "load_price_conditions", lambda *a, **k: {"items": []})
    calls = []
    def verified(root, symbol, source, *, now):
        calls.append(source["case_path"])
        return {"symbol": symbol, "action": "no_order", "signal_state": "TRIGGER_REJECTED",
            "action_intent": "EXIT", "data_available_at": "2026-10-14T20:00:00+08:00"}
    monkeypatch.setattr(continuity, "load_held_price_plan", verified)
    client, secret = client_for(tmp_path, path, monkeypatch)
    unlock(client, secret)
    before = path.read_bytes()
    response = client.get(ROUTE)
    assert response.status_code == 200
    result = response.json()
    assert result["revision"] == client.get("/api/v1/portfolio").json()["revision"] == 3
    assert result["items"][0]["quantity"] == "200"
    assert result["items"][0]["review_priority"] == 0
    assert result["items"][0]["selected_today"] is False
    assert calls == [binding["case_path"]]
    assert path.read_bytes() == before


def test_explicit_refresh_auth_revision_and_persisted_case_discovery_without_ledger_write(tmp_path, monkeypatch):
    path = tmp_path / "TEST_ONLY-refresh.jsonl"
    initialize(path)
    client, secret = client_for(tmp_path, path, monkeypatch)
    route = ROUTE + "/refresh"
    assert client.post(route, json={"expected_revision": 1}).status_code == 401
    unlock(client, secret)
    client.headers["origin"] = "http://example.invalid"
    assert client.post(route, json={"expected_revision": 1}).status_code == 403
    client.headers["origin"] = "http://127.0.0.1:8791"
    calls = []
    def bundle(symbols):
        calls.append(symbols)
        return {"references": {"600887": {"document_refs": {"tencent": "TEST_ONLY"}}},
            "documents": {"TEST_ONLY": {}}, "status": "TEST_ONLY"}
    monkeypatch.setattr(continuity, "collect_session_bundle", bundle)
    monkeypatch.setattr(continuity, "parse_quote", lambda *a, **k: {"price": "20"})
    monkeypatch.setattr(continuity, "evaluate_quote_session", lambda *a, **k:
        {"passed": True, "expected_session": "2026-10-16"})
    def collect(**kwargs):
        assert kwargs["observation_scope"] == "LAST_COMPLETED_CLOSE_DISPLAY_ONLY"
        case = tmp_path / "runtime/hotspot-current-price-cases/600887-2026-10-16-TEST_ONLY/case.json"
        case.parent.mkdir(parents=True)
        case.write_text("{}", encoding="utf-8")
        return {"case_path": str(case.relative_to(tmp_path)),
                "case_sha256": hashlib.sha256(case.read_bytes()).hexdigest()}
    monkeypatch.setattr(continuity, "collect_current_price_case", collect)
    def verify(root, symbol, binding, *, now):
        target = root / binding["case_path"]
        assert hashlib.sha256(target.read_bytes()).hexdigest() == binding["case_sha256"]
        return {"symbol": symbol, "action": "no_order", "case_path": binding["case_path"],
            "case_sha256": binding["case_sha256"], "market_trade_date": "2026-10-16",
            "data_available_at": "2026-10-10T20:00:00+08:00", "signal_state": "TRIGGER_REJECTED",
            "action_intent": "EXIT"}
    monkeypatch.setattr(continuity, "load_held_price_plan", verify)
    monkeypatch.setattr(continuity, "load_price_conditions", lambda *a, **k: {"items": []})
    monkeypatch.setattr(continuity, "load_registered_value_action_plans", lambda *a, **k: {"items": []})
    before = path.read_bytes()
    assert client.post(route, json={"expected_revision": 0}).status_code == 409
    assert client.post(route, json={"expected_revision": 1, "symbols": ["999999"]}).status_code == 422
    assert calls == []
    response = client.post(route, json={"expected_revision": 1})
    assert response.status_code == 200
    refreshed = response.json()
    assert refreshed["schema_version"] == "private-held-continuity-refresh-v1"
    assert refreshed["status"] == "REFRESHED"
    assert refreshed["items"][0]["observation_scope"] == "LAST_COMPLETED_CLOSE_DISPLAY_ONLY"
    assert refreshed["items"][0]["current_pit"] is refreshed["items"][0]["formal_eligibility"] is False
    assert refreshed["ledger_written"] is refreshed["public_registry_written"] is False
    # A fresh provider instance (as on restart) finds existing immutable case
    # history, without any public or private membership-pointer file.
    result = client.get(ROUTE).json()
    assert result["revision"] == refreshed["revision"] == 1
    assert result["items"][0]["review_priority"] == 0
    assert result["items"][0]["strategy_plan"]["market_trade_date"] == "2026-10-16"
    assert not (tmp_path / "config/current-price-conditions.json").exists()
    reused = client.post(route, json={"expected_revision": 1}).json()
    assert reused["items"][0]["evidence_status"] == "REUSED_VERIFIED_LATEST_COMPLETED_CASE"
    assert calls == [["600887"]]
    assert path.read_bytes() == before


@pytest.mark.parametrize("timing_gap", [False, True])
def test_refresh_source_failure_is_explicit_and_does_not_discard_holding(tmp_path, monkeypatch, timing_gap):
    path = tmp_path / "TEST_ONLY-failure.jsonl"
    initialize(path)
    client, secret = client_for(tmp_path, path, monkeypatch)
    unlock(client, secret)
    def unavailable(symbols):
        if timing_gap:
            raise ValueError("B1 requires same-session post-close acquisition")
        raise OSError("TEST_ONLY source unavailable")
    monkeypatch.setattr(continuity, "collect_session_bundle", unavailable)
    before = path.read_bytes()
    response = client.post(ROUTE + "/refresh", json={"expected_revision": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PARTIAL"
    assert body["failures"][0]["symbol"] == "600887"
    assert body["failures"][0]["gap_category"] == ("ENGINEERING" if timing_gap else "DATA")
    if timing_gap:
        assert body["failures"][0]["gap_code"] == "HELD_NEXT_MORNING_CASE_COLLECTION_UNSUPPORTED"
    else:
        assert "source unavailable" in body["failures"][0]["reason"]
    assert client.get(ROUTE).json()["items"][0]["quantity"] == "100"
    assert path.read_bytes() == before


def test_refresh_caps_each_request_and_reports_remaining_holdings(tmp_path, monkeypatch):
    path = tmp_path / "TEST_ONLY-many.jsonl"
    service = PrivatePortfolioService(PrivateJournal(path))
    symbols = [f"60000{i}" for i in range(6)]
    service.initialize({"idempotency_key": "init", "expected_revision": 0,
        "account_scope": "TEST_ONLY", "as_of": "2026-10-10", "cash_cny": "8000",
        "holdings": [{"symbol": s, "exchange": "SSE", "quantity": "100", "cost_basis_cny": "2000"} for s in symbols],
        "sleeve_allocations": {s: {"CORE_VALUE": "100"} for s in symbols}, "policy": {},
        "confirmed_at": "2026-10-10T20:00:00+08:00", "confirmation_note": "TEST_ONLY"})
    calls = []
    def unavailable(requested):
        calls.extend(requested)
        raise OSError("TEST_ONLY")
    monkeypatch.setattr(continuity, "collect_session_bundle", unavailable)
    client, secret = client_for(tmp_path, path, monkeypatch)
    unlock(client, secret)
    assert client.post(ROUTE + "/refresh", json={"expected_revision": 1, "symbols": symbols}).status_code == 422
    result = client.post(ROUTE + "/refresh", json={"expected_revision": 1}).json()
    assert len(calls) == 5
    assert result["unprocessed_symbols"] == [symbols[-1]]
    assert result["status"] == "PARTIAL"


def test_unsupported_held_asset_is_reported_and_never_dropped(tmp_path, monkeypatch):
    path = tmp_path / "TEST_ONLY-unsupported.jsonl"
    service = PrivatePortfolioService(PrivateJournal(path))
    service.initialize({"idempotency_key": "init", "expected_revision": 0,
        "account_scope": "TEST_ONLY", "as_of": "2026-10-10", "cash_cny": "8000",
        "holdings": [{"symbol": "830001", "exchange": "BSE", "quantity": "100", "cost_basis_cny": "2000"}],
        "sleeve_allocations": {"830001": {"CORE_VALUE": "100"}}, "policy": {},
        "confirmed_at": "2026-10-10T20:00:00+08:00", "confirmation_note": "TEST_ONLY"})
    monkeypatch.setattr(continuity, "collect_session_bundle", lambda *a, **k: pytest.fail("unsupported asset must not fetch"))
    client, secret = client_for(tmp_path, path, monkeypatch)
    unlock(client, secret)
    before = path.read_bytes()
    body = client.post(ROUTE + "/refresh", json={"expected_revision": 1}).json()
    assert body["status"] == "PARTIAL"
    assert body["failures"][0]["gap_code"] == "HELD_SECURITY_COLLECTOR_UNSUPPORTED"
    held = client.get(ROUTE).json()["items"][0]
    assert held["symbol"] == "830001" and held["quantity"] == "100"
    assert "CURRENT_STRATEGY_PLAN_UNAVAILABLE" in held["data_gaps"]
    assert path.read_bytes() == before
