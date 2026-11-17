"""TL11-P3 isolated journal; no production private-root resolution."""
from decimal import Decimal

import pytest

from value_investment_agent.application.portfolio.private_portfolio_service import (
    PrivateJournal, PrivatePortfolioService, JournalConflict, JournalValidationError,
)
from value_investment_agent.application.portfolio.private_risk_projection import build_risk_input, review_private_risk_rehearsal
from datetime import date, datetime


@pytest.fixture
def ledger(tmp_path):
    service = PrivatePortfolioService(PrivateJournal(tmp_path / "test-journal.jsonl"))
    service.initialize({
        "idempotency_key": "test-init", "expected_revision": 0,
        "account_scope": "TEST_ONLY", "as_of": "2026-10-10",
        "cash_cny": "5000", "holdings": [{"symbol": "600887", "exchange": "SSE",
        "quantity": "200", "cost_basis_cny": "2000"}],
        "sleeve_allocations": {"600887": {"CORE_VALUE": "100", "HOTSPOT_SATELLITE": "100"}},
        "policy": {}, "confirmation_note": "TEST ONLY",
        "confirmed_at": "2026-10-10T20:00:00+08:00",
    })
    return service


def request(ledger, *, side="BUY", sleeve="CORE_VALUE", transaction="test-buy", price="20"):
    return {"idempotency_key": transaction, "expected_revision": len(ledger.records()),
        "fill": {"transaction_id": transaction, "symbol": "600887", "exchange": "SSE",
        "side": side, "sleeve": sleeve, "quantity": "100", "price_cny": price,
        "fees_cny": "5", "trade_date": "2026-10-12", "trading_unit": "100",
        "next_sell_session": "2026-10-13" if side == "BUY" else None,
        "decision_id": "test-real-research-reference", "research_version": "published-v5"}}


def confirm(ledger, digest, key):
    body = {"idempotency_key": key, "expected_revision": len(ledger.records()),
        "prepared_record_sha256": digest, "confirmation_note": "TEST ONLY",
        "confirmed_at": "2026-10-12T21:00:00+08:00"}
    first = ledger.confirm_fill(body)
    assert ledger.confirm_fill(body) == first
    return first[0]


def test_buy_sell_replay_shared_cash_and_exact_sleeve_costs(ledger):
    buy = request(ledger)
    _, digest = ledger.prepare_fill(buy)
    assert ledger.prepare_fill(buy)[1] == digest
    assert ledger.portfolio_view()["cash_cny"] == "5000"
    draft_risk = review_private_risk_rehearsal(ledger.journal,
        generated_at=datetime.fromisoformat("2026-10-14T20:00:00+08:00"), today=date(2026, 10, 14))
    assert draft_risk["facts"]["cash_cny"] == "5000"
    assert draft_risk["facts"]["confirmed_fill_count"] == 0
    confirmed = confirm(ledger, digest, "test-confirm-buy")
    assert confirmed["cash_cny"] == "2995"
    assert confirmed["trades"][0]["research_version"] == "published-v5"
    replay = PrivatePortfolioService(ledger.journal)
    assert replay.portfolio_view()["trades"][0]["decision_id"] == "test-real-research-reference"
    sleeves = {row["sleeve"]: row for row in confirmed["positions"][0]["sleeves"]}
    assert sleeves["CORE_VALUE"]["quantity"] == "200"
    assert sleeves["HOTSPOT_SATELLITE"]["quantity"] == "100"
    unavailable = request(ledger, side="SELL", transaction="test-t-plus-one")
    unavailable["fill"]["quantity"] = "200"
    with pytest.raises(JournalValidationError):
        ledger.prepare_fill(unavailable)
    # The other sleeve cannot spend the original account cash again.
    with pytest.raises(JournalValidationError, match="insufficient cash"):
        ledger.prepare_fill(request(ledger, sleeve="HOTSPOT_SATELLITE", transaction="test-overdraft", price="40"))
    _, sell_digest = ledger.prepare_fill(request(ledger, side="SELL", sleeve="HOTSPOT_SATELLITE", transaction="test-sell", price="15"))
    sold = confirm(ledger, sell_digest, "test-confirm-sell")
    assert sold["cash_cny"] == "4490"
    assert sold["realized_pnl_cny"] == "495"
    assert Decimal(sold["positions"][0]["cost_cny"]) == Decimal("3005")
    assert sold["positions"][0]["quantity"] == "200"
    with pytest.raises(JournalValidationError):
        ledger.prepare_fill(request(ledger, side="SELL", sleeve="HOTSPOT_SATELLITE", transaction="test-wrong-sleeve"))
    with pytest.raises(JournalConflict) as error:
        ledger.prepare_fill(request(ledger, transaction="test-buy"))
    assert error.value.code in {"IDEMPOTENCY_CONFLICT", "DUPLICATE_TRANSACTION"}
    projected = build_risk_input(ledger._replay(ledger.records()), sellable_as_of=date(2026, 10, 14))
    assert projected["portfolio"]["snapshot"]["cash_cny"] == "4490"
    assert projected["portfolio"]["snapshot"]["holdings"][0]["quantity"] == "200"
    risk = review_private_risk_rehearsal(ledger.journal,
        generated_at=datetime.fromisoformat("2026-10-14T20:00:00+08:00"), today=date(2026, 10, 14))
    assert risk["facts"]["cash_cny"] == "4490"
    assert risk["facts"]["confirmed_fill_count"] == 2
    assert risk["engine"]["position_guidance"] is None
    assert risk["engine"]["trade_eligible"] is False
    assert "investable_assets_cny" in risk["blockers"]


@pytest.mark.parametrize("field", ["price_cny", "quantity", "trade_date", "fees_cny", "research_version"])
def test_missing_actual_inputs_or_partial_context_cannot_write(ledger, field):
    body = request(ledger)
    del body["fill"][field]
    with pytest.raises(JournalValidationError):
        ledger.prepare_fill(body)
    assert len(ledger.records()) == 1


def test_unlinked_legacy_fill_still_confirms_and_replays(ledger):
    body = request(ledger)
    del body["fill"]["decision_id"]
    del body["fill"]["research_version"]
    _, digest = ledger.prepare_fill(body)
    confirm(ledger, digest, "test-unlinked-confirm")
    trade = PrivatePortfolioService(ledger.journal).portfolio_view()["trades"][0]
    assert trade["decision_id"] is None
    assert trade["research_version"] is None
    assert trade["price_cny"] == "20"
