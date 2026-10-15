"""TEST_ONLY ledger positions; public market replay never implies actual holdings."""
from copy import deepcopy
from datetime import datetime

import pytest

from test_private_ips_policy import service
from value_investment_agent.application.portfolio.held_continuity import (
    project_held_continuity, review_held_continuity,
)

NOW = datetime.fromisoformat("2026-10-15T20:00:00+08:00")


def position(symbol, sleeve="HOTSPOT_SATELLITE", sellable="100"):
    return {"symbol": symbol, "exchange": "SZSE", "quantity": "100",
        "sleeves": [{"sleeve": sleeve, "quantity": "100",
                     "sellable_quantity": sellable, "next_sell_session": "2026-10-16"}]}


def plan(symbol, **fields):
    return {"symbol": symbol, "action": "no_order", "data_available_at": NOW.isoformat(),
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
    assert row["position_guidance"] is None


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
