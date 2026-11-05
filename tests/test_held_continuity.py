"""TEST_ONLY ledger positions; public market replay never implies actual holdings."""
from copy import deepcopy
from datetime import datetime

import pytest

from test_private_ips_policy import service
from value_investment_agent.application.portfolio.held_continuity import (
    project_held_continuity, review_held_continuity,
)
from value_investment_agent.application.portfolio import held_continuity as continuity

NOW = datetime.fromisoformat("2026-10-15T20:00:00+08:00")


def position(symbol, sleeve="HOTSPOT_SATELLITE", sellable="100"):
    return {"symbol": symbol, "exchange": "SZSE", "quantity": "100",
        "sleeves": [{"sleeve": sleeve, "quantity": "100",
                     "sellable_quantity": sellable, "next_sell_session": "2026-10-16"}]}


def plan(symbol, **fields):
    return {"symbol": symbol, "action": "no_order", "data_available_at": NOW.isoformat(),
        "schema_version": "price-action-plan-current-v1", "strategy": "HOTSPOT_SATELLITE",
        "signal_state": "TRIGGER_REJECTED", "action_intent": "EXIT", **fields}


def project(positions, provider, risk=None, selected=()):
    return project_held_continuity(positions, risk or {"blockers": ["TEST_ONLY_RISK_GAP"],
        "engine": {"position_guidance": None}}, selected_symbols=selected,
        plan_provider=provider, generated_at=NOW)


def test_all_holdings_survive_multiple_ranking_exits_and_retention_cap():
    positions = [position(f"{i:06d}") for i in range(20)]
    positions.append(position("600887", "CORE_VALUE"))
    before = deepcopy(positions)
    for selected in [("000001",), (), ("999999",)]:
        result = project(positions, lambda symbol: plan(symbol), selected=selected)
        assert len(result["items"]) == 21
        assert {row["symbol"] for row in result["items"]} == {p["symbol"] for p in positions}
        assert all(row["personal_sell_permission"] is False for row in result["items"])
    assert positions == before


def test_exit_priority_survives_t_plus_one_and_risk_gaps():
    result = project([position("000001"), position("000002", sellable="0")],
        lambda symbol: plan(symbol, action_intent="WATCH", signal_state="CONDITION_PENDING")
        if symbol == "000001" else plan(symbol))
    row = result["items"][0]
    assert row["symbol"] == "000002"
    assert row["sellable_quantity"] == "0"
    assert row["review_priority"] == 0
    assert "T_PLUS_ONE_OR_SELLABLE_LIMIT" in row["review_reasons"]
    assert "TEST_ONLY_RISK_GAP" in row["data_gaps"]
    assert row["announcement_coverage_status"] == "UNKNOWN"
    assert "ANNOUNCEMENT_COVERAGE_UNKNOWN" in row["data_gaps"]
    assert row["position_guidance"] is None


def test_announcement_coverage_is_complete_only_with_explicit_plan_evidence():
    unknown = project([position("000001")], lambda symbol: plan(symbol))["items"][0]
    complete = project([position("000001")], lambda symbol: plan(
        symbol, announcement_coverage_status="COMPLETE"))["items"][0]
    assert unknown["announcement_coverage_status"] == "UNKNOWN"
    assert "ANNOUNCEMENT_COVERAGE_UNKNOWN" in unknown["data_gaps"]
    assert complete["announcement_coverage_status"] == "COMPLETE"
    assert "ANNOUNCEMENT_COVERAGE_UNKNOWN" not in complete["data_gaps"]


@pytest.mark.parametrize("failure", ["missing", "corrupt", "future", "foreign", "stale"])
def test_provider_failure_preserves_held_facts_without_current_exit_claim(failure):
    def provider(symbol):
        if failure == "missing":
            return None
        if failure == "corrupt":
            raise ValueError("TEST_ONLY source hash mismatch")
        if failure == "future":
            return plan(symbol, data_available_at="2026-10-16T20:00:00+08:00")
        if failure == "foreign":
            return plan("999999")
        return plan(symbol, signal_state="STALE")
    row = project([position("300364")], provider)["items"][0]
    assert row["quantity"] == "100"
    assert "CURRENT_STRATEGY_PLAN_UNAVAILABLE" in row["data_gaps"]
    assert "INVALIDATION_OR_EXIT_REVIEW" not in row["review_reasons"]


def test_read_only_existing_journal_risk_and_sellable_path(service, tmp_path):
    before = service.journal.path.read_bytes()
    result = review_held_continuity(service.journal, repository_root=tmp_path,
        generated_at=NOW, plan_provider=lambda symbol: None)
    row = result["items"][0]
    assert row["symbol"] == "300364" and not row["selected_today"]
    assert row["sleeves"][0]["sleeve"] == "CORE_VALUE"
    assert result["risk"]["engine"]["position_guidance"] is None
    assert result["risk"]["blockers"]
    assert service.journal.path.read_bytes() == before


def test_future_account_has_no_current_sellability():
    risk = {"facts": {"valuation_blockers": ["ACCOUNT_AS_OF_IN_FUTURE"]}}
    row = project([position("300364")], lambda symbol: None, risk)["items"][0]
    assert row["sellable_quantity"] is None
    assert "ACCOUNT_AS_OF_IN_FUTURE" in row["data_gaps"]


def test_closed_positions_retire_but_open_positions_remain():
    closed = {**position("000001"), "quantity": "0"}
    assert [r["symbol"] for r in project([closed, position("000002")], lambda s: None)["items"]] == ["000002"]


def test_real_engine_t_plus_one_releases_only_on_recorded_next_session(service, tmp_path):
    _, digest = service.prepare_fill({"idempotency_key": "buy", "expected_revision": 1,
        "fill": {"transaction_id": "TEST_ONLY-buy", "side": "BUY", "sleeve": "CORE_VALUE",
            "symbol": "300364", "exchange": "SZSE", "quantity": "100", "price_cny": "30",
            "fees_cny": "5", "trade_date": "2026-10-15", "next_sell_session": "2026-10-16",
            "trading_unit": "100"}})
    service.confirm_fill({"idempotency_key": "confirm", "expected_revision": 2,
        "prepared_record_sha256": digest, "confirmed_at": "2026-10-15T16:00:00+08:00",
        "confirmation_note": "TEST_ONLY actual-engine isolated fill"})
    before = service.journal.path.read_bytes()
    for clock, expected in [(NOW, "100"),
            (datetime.fromisoformat("2026-10-16T20:00:00+08:00"), "200")]:
        result = review_held_continuity(service.journal, repository_root=tmp_path,
            generated_at=clock, plan_provider=lambda symbol: None)
        assert result["items"][0]["quantity"] == "200"
        assert result["items"][0]["sellable_quantity"] == expected
    assert service.journal.path.read_bytes() == before


@pytest.mark.parametrize("held_sleeve,plan_sleeve,schema", [
    ("CORE_VALUE", "HOTSPOT_SATELLITE", "price-action-plan-current-v1"),
    ("HOTSPOT_SATELLITE", "CORE_VALUE", "value-action-plan-v1"),
])
def test_other_sleeve_plan_cannot_supply_exit_or_downtrend(held_sleeve, plan_sleeve, schema):
    row = project([position("300364", held_sleeve)], lambda symbol: plan(symbol,
        schema_version=schema, strategy=plan_sleeve,
        price_behavior={"daily_trend": "DOWNTREND", "structural_invalidation": True},
        announcement_coverage_status="COMPLETE"))["items"][0]
    assert row["quantity"] == "100"
    assert row["strategy_plan"] is None
    assert "INVALIDATION_OR_EXIT_REVIEW" not in row["review_reasons"]
    assert "DAILY_DOWNTREND_REVIEW" not in row["review_reasons"]
    assert "CURRENT_STRATEGY_PLAN_UNAVAILABLE" in row["data_gaps"]
    assert row["announcement_coverage_status"] == "UNKNOWN"


@pytest.mark.parametrize("value_available", [True, False])
def test_default_resolver_follows_actual_sleeves_after_full_hotspot_sale(service, tmp_path, monkeypatch, value_available):
    hotspot = plan("300364", schema_version="price-action-plan-current-v1", strategy="HOTSPOT_SATELLITE")
    value = plan("300364", schema_version="value-action-plan-v1", strategy="CORE_VALUE",
                 action_intent="WATCH", signal_state="CONDITION_PENDING")
    monkeypatch.setattr(continuity, "load_price_conditions", lambda *a, **k:
                        {"items": [{"symbol": "300364", "price_action_plan": hotspot}]})
    monkeypatch.setattr(continuity, "load_current_value_action_plans", lambda *a, **k:
                        {"items": [value] if value_available else []})
    monkeypatch.setattr(continuity, "_case_history", lambda *a: [])

    def fill(side, day, sleeve="HOTSPOT_SATELLITE"):
        revision = len(service.records())
        body = {"transaction_id": f"TEST_ONLY-{side}-{sleeve}", "side": side, "sleeve": sleeve,
                "symbol": "300364", "exchange": "SZSE", "quantity": "100", "price_cny": "20",
                "fees_cny": "1", "trade_date": day}
        if side == "BUY":
            body.update(next_sell_session="2026-10-15", trading_unit="100")
        _, digest = service.prepare_fill({"idempotency_key": f"prepare-{side}-{sleeve}",
                                         "expected_revision": revision, "fill": body})
        service.confirm_fill({"idempotency_key": f"confirm-{side}-{sleeve}", "expected_revision": revision + 1,
            "prepared_record_sha256": digest, "confirmed_at": day + "T16:00:00+08:00",
            "confirmation_note": "TEST_ONLY confirmed manual fill"})

    fill("BUY", "2026-10-14")
    before = service.journal.path.read_bytes()
    both = review_held_continuity(service.journal, repository_root=tmp_path, generated_at=NOW)["items"][0]
    assert both["quantity"] == "200" and len(both["sleeves"]) == 2
    assert "INVALIDATION_OR_EXIT_REVIEW" in both["review_reasons"]
    assert service.journal.path.read_bytes() == before
    fill("SELL", "2026-10-15")
    def no_hotspot_history(*args):
        pytest.fail("Core-only holdings must not resolve hotspot case history")

    monkeypatch.setattr(continuity, "_case_history", no_hotspot_history)
    _, provider = continuity.build_held_plan_provider(tmp_path, service._replay(service.records()), now=NOW)
    resolved = provider("300364")
    assert (resolved is not None) == value_available
    # Account mark-to-market may reuse a verified case price for either sleeve;
    # only the strategy resolver must stop using its hotspot decision reasons.
    monkeypatch.setattr(continuity, "_case_history", lambda *a: [])
    before = service.journal.path.read_bytes()
    core = review_held_continuity(service.journal, repository_root=tmp_path, generated_at=NOW)["items"][0]
    assert core["quantity"] == "100"
    assert [s["sleeve"] for s in core["sleeves"]] == ["CORE_VALUE"]
    if value_available:
        assert core["strategy_plan"]["strategy"] == "CORE_VALUE"
    else:
        assert core["strategy_plan"] is None
        assert "CURRENT_STRATEGY_PLAN_UNAVAILABLE" in core["data_gaps"]
    assert "INVALIDATION_OR_EXIT_REVIEW" not in core["review_reasons"]
    assert service.journal.path.read_bytes() == before
    fill("SELL", "2026-10-15", sleeve="CORE_VALUE")
    before = service.journal.path.read_bytes()
    closed = review_held_continuity(service.journal, repository_root=tmp_path, generated_at=NOW)
    assert closed["items"] == [] and closed["status"] == "NO_HELD_SECURITIES"
    assert service.journal.path.read_bytes() == before


@pytest.mark.parametrize("fault", ["zero_quantity", "schema_strategy_conflict", "unknown_schema", "missing_sleeves"])
def test_unbound_or_empty_sleeve_cannot_emit_exit(fault):
    held = position("300364", "CORE_VALUE")
    candidate = plan("300364")
    if fault == "zero_quantity":
        held["sleeves"].append({"sleeve": "HOTSPOT_SATELLITE", "quantity": "0", "sellable_quantity": "0"})
    elif fault == "schema_strategy_conflict":
        candidate["strategy"] = "CORE_VALUE"
    elif fault == "unknown_schema":
        candidate.update(schema_version="unknown", strategy="CORE_VALUE")
    else:
        held.pop("sleeves")
    row = project([held], lambda symbol: candidate)["items"][0]
    assert row["quantity"] == "100" and row["strategy_plan"] is None
    assert "INVALIDATION_OR_EXIT_REVIEW" not in row["review_reasons"]
    assert "CURRENT_STRATEGY_PLAN_UNAVAILABLE" in row["data_gaps"]


def test_same_security_resolves_both_held_strategy_plans(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from decimal import Decimal
    hotspot = plan('300364')
    core = dict(symbol='300364', action='no_order', schema_version='value-action-plan-v1', strategy='CORE_VALUE')
    monkeypatch.setattr(continuity, 'load_price_conditions', lambda *a, **k:
        dict(items=[dict(symbol='300364', price_action_plan=hotspot)]))
    monkeypatch.setattr(continuity, 'load_current_value_action_plans', lambda *a, **k: dict(items=[core]))
    replayed = SimpleNamespace(trades=[], state=SimpleNamespace(lots=[
        SimpleNamespace(symbol='300364', sleeve=sleeve, quantity=Decimal(100))
        for sleeve in ('CORE_VALUE', 'HOTSPOT_SATELLITE')]))
    _, provider = continuity.build_held_plan_provider(tmp_path, replayed, now=NOW)
    assert provider.for_sleeve('300364', 'CORE_VALUE')['strategy'] == 'CORE_VALUE'
    assert provider.for_sleeve('300364', 'HOTSPOT_SATELLITE')['strategy'] == 'HOTSPOT_SATELLITE'
    assert provider.for_sleeve('300364', 'OTHER') is None
