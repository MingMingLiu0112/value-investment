"""Durable private portfolio journal: hash chain, idempotency and fail-closed."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from value_investment_agent.application.portfolio.private_portfolio_service import (
    JournalConflict,
    JournalValidationError,
    PrivateJournal,
    PrivatePortfolioService,
    PrivateStoreUnavailable,
    resolve_private_root,
)

REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.fixture()
def service(monkeypatch):
    # The private root guard requires a location outside every Git worktree, so
    # pytest's own temporary directory (often inside the repository) cannot host it.
    root = Path(tempfile.mkdtemp(prefix="vi-private-", dir=Path.home()))
    monkeypatch.setenv("VALUE_INVESTMENT_PRIVATE_ROOT", str(root))
    try:
        yield PrivatePortfolioService(
            PrivateJournal(resolve_private_root(repository_root=REPOSITORY)))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _initialize_request(**overrides):
    request = {
        "idempotency_key": "init-1",
        "expected_revision": 0,
        "account_scope": "acct-demo",
        "as_of": "2026-10-10",
        "cash_cny": "500000.00",
        "holdings": [{"symbol": "600519", "exchange": "SSE", "quantity": "1000",
                      "cost_basis_cny": "1500000.00"}],
        "sleeve_allocations": {"600519": {"CORE_VALUE": "600", "HOTSPOT_SATELLITE": "400"}},
        "policy": {"investable_assets_cny": "2000000", "max_single_security_pct": "10"},
        "confirmation_note": "initial confirm",
        "confirmed_at": "2026-10-10T20:00:00+08:00",
    }
    request.update(overrides)
    return request


def _fill_request(**overrides):
    request = {
        "idempotency_key": "fill-1",
        "expected_revision": 1,
        "fill": {"transaction_id": "T1", "side": "BUY", "sleeve": "CORE_VALUE",
                 "symbol": "600519", "exchange": "SSE", "quantity": "200",
                 "price_cny": "1500.00", "fees_cny": "5.00", "trade_date": "2026-10-12",
                 "next_sell_session": "2026-10-13", "trading_unit": "100"},
    }
    request.update(overrides)
    return request


def test_missing_root_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("VALUE_INVESTMENT_PRIVATE_ROOT", str(tmp_path / "absent"))
    with pytest.raises(PrivateStoreUnavailable):
        resolve_private_root(repository_root=REPOSITORY)


def test_root_inside_repository_is_rejected(monkeypatch):
    monkeypatch.setenv("VALUE_INVESTMENT_PRIVATE_ROOT", str(REPOSITORY))
    with pytest.raises(PrivateStoreUnavailable):
        resolve_private_root(repository_root=REPOSITORY)


def test_synced_root_is_rejected(tmp_path, monkeypatch):
    synced = tmp_path / "WPSDrive" / "private"
    synced.mkdir(parents=True)
    monkeypatch.setenv("VALUE_INVESTMENT_PRIVATE_ROOT", str(synced))
    with pytest.raises(PrivateStoreUnavailable):
        resolve_private_root(repository_root=REPOSITORY)


def test_empty_journal_is_not_connected(service):
    view = service.portfolio_view()
    assert view["status"] == "NOT_CONNECTED"
    assert view["action"] == "no_order"
    assert view["positions"] == []
    assert "PRIVATE_PORTFOLIO_NOT_CONNECTED" in view["blockers"]
    assert service.records() == []


@pytest.mark.parametrize(
    "trade_date, next_sell_session, message",
    [
        ("2026-10-10", "2026-10-12", "trade date is not a covered exchange session"),
        ("2026-09-30", "2026-10-01", "next covered exchange session: 2026-10-08"),
    ],
)
def test_prepare_fill_rejects_non_session_dates(
    service, trade_date, next_sell_session, message
):
    service.initialize(_initialize_request())
    request = _fill_request()
    request["fill"]["trade_date"] = trade_date
    request["fill"]["next_sell_session"] = next_sell_session
    with pytest.raises(JournalValidationError, match=message):
        service.prepare_fill(request)
    assert len(service.records()) == 1


def test_full_lifecycle_keeps_arithmetic_in_python(service):
    baseline, baseline_digest = service.initialize(_initialize_request())
    assert baseline["status"] == "BASELINE_CONFIRMED"
    assert baseline["revision"] == 1
    assert len(baseline_digest) == 64
    assert baseline["cash_cny"] == "500000.00"
    position = baseline["positions"][0]
    assert position["quantity"] == "1000"
    assert {row["sleeve"]: row["quantity"] for row in position["sleeves"]} == {
        "CORE_VALUE": "600", "HOTSPOT_SATELLITE": "400"}
    assert position["market_value_cny"] is None
    assert baseline["valuation"]["status"] == "PRICE_NOT_ADMITTED"

    draft, draft_digest = service.prepare_fill(_fill_request())
    assert draft["status"] == "FILL_PREPARED"
    assert draft["revision"] == 2
    assert draft["draft"]["cash_cny"] == "199995.00"
    assert draft["draft"]["positions"][0]["quantity"] == "1200"
    assert service.portfolio_view()["cash_cny"] == "500000.00"
    assert service.portfolio_view()["pending_draft"] is not None

    confirmed, _ = service.confirm_fill({
        "idempotency_key": "fill-1-confirm", "expected_revision": 2,
        "prepared_record_sha256": draft_digest,
        "confirmed_at": "2026-10-12T21:00:00+08:00", "confirmation_note": "confirmed"})
    assert confirmed["status"] == "FILL_CONFIRMED"
    assert confirmed["cash_cny"] == "199995.00"
    assert confirmed["realized_pnl_cny"] == "0"
    core = next(row for row in confirmed["positions"][0]["sleeves"] if row["sleeve"] == "CORE_VALUE")
    assert core["quantity"] == "800"
    assert confirmed["pending_draft"] is None

    reconciled, _ = service.reconcile({
        "idempotency_key": "reconcile-1", "expected_revision": 3,
        "reconciled_at": "2026-10-12T21:05:00+08:00", "confirmation_note": "reconciled"})
    assert reconciled["status"] == "RECONCILED"
    holdings = reconciled["snapshot"]["holdings"]
    assert holdings[0]["quantity"] == "1200"
    assert holdings[0]["cost_basis_cny"] == "1800005.00"
    assert holdings[0]["market_value_cny"] is None
    assert holdings[0]["quantity_source"] == "HUMAN_CONFIRMED"

    view = service.portfolio_view()
    assert view["status"] == "CONNECTED"
    assert view["revision"] == 4
    assert len(view["trades"]) == 1
    assert view["trades"][0]["transaction_id"] == "T1"


def test_replayed_key_returns_stored_response(service):
    first, first_digest = service.initialize(_initialize_request())
    second, second_digest = service.initialize(_initialize_request())
    assert first == second
    assert first_digest == second_digest
    assert len(service.records()) == 1


def test_reused_key_with_new_content_is_conflict(service):
    service.initialize(_initialize_request())
    with pytest.raises(JournalConflict) as error:
        service.initialize(_initialize_request(cash_cny="1.00"))
    assert error.value.code == "IDEMPOTENCY_CONFLICT"


def test_second_initialize_is_conflict(service):
    service.initialize(_initialize_request())
    with pytest.raises(JournalConflict) as error:
        service.initialize(_initialize_request(idempotency_key="init-2"))
    assert error.value.code == "ALREADY_INITIALIZED"


def test_stale_revision_is_conflict(service):
    service.initialize(_initialize_request())
    with pytest.raises(JournalConflict) as error:
        service.prepare_fill(_fill_request(expected_revision=7))
    assert error.value.code == "VERSION_CONFLICT"


def test_fill_before_baseline_is_conflict(service):
    with pytest.raises(JournalConflict) as error:
        service.prepare_fill(_fill_request(expected_revision=0))
    assert error.value.code == "NOT_CONNECTED"


def test_duplicate_transaction_is_conflict(service):
    service.initialize(_initialize_request())
    _, draft_digest = service.prepare_fill(_fill_request())
    service.confirm_fill({"idempotency_key": "fill-1-confirm", "expected_revision": 2,
                          "prepared_record_sha256": draft_digest,
                          "confirmed_at": "2026-10-12T21:00:00+08:00",
                          "confirmation_note": "confirmed"})
    with pytest.raises(JournalConflict) as error:
        service.prepare_fill(_fill_request(idempotency_key="fill-2", expected_revision=3))
    assert error.value.code == "DUPLICATE_TRANSACTION"


def test_confirm_without_matching_draft_is_conflict(service):
    service.initialize(_initialize_request())
    with pytest.raises(JournalConflict) as error:
        service.confirm_fill({"idempotency_key": "confirm-1", "expected_revision": 1,
                              "prepared_record_sha256": "0" * 64,
                              "confirmed_at": "2026-10-12T21:00:00+08:00",
                              "confirmation_note": "no draft"})
    assert error.value.code == "NO_CONFIRMABLE_DRAFT"


def test_unconfirmed_draft_blocks_second_draft(service):
    service.initialize(_initialize_request())
    service.prepare_fill(_fill_request())
    with pytest.raises(JournalConflict) as error:
        service.prepare_fill(_fill_request(idempotency_key="fill-2", expected_revision=2))
    assert error.value.code == "PENDING_DRAFT_EXISTS"


def test_cancelled_draft_is_voided_without_changing_holdings(service):
    service.initialize(_initialize_request())
    _, draft_digest = service.prepare_fill(_fill_request())
    cancelled, _ = service.cancel_fill({
        "idempotency_key": "cancel-1", "expected_revision": 2,
        "prepared_record_sha256": draft_digest,
        "cancelled_at": "2026-10-12T20:30:00+08:00", "reason": "录入有误"})
    assert cancelled["status"] == "FILL_CANCELLED"
    assert cancelled["revision"] == 3
    assert cancelled["cancelled_transaction_id"] == "T1"
    view = service.portfolio_view()
    assert view["cash_cny"] == "500000.00"
    assert view["positions"][0]["quantity"] == "1000"
    assert view["trades"] == []
    assert view["pending_draft"] is None
    assert len(view["blockers"]) == 1
    records = service.records()
    assert [record["kind"] for record in records] == [
        "BASELINE_CONFIRMED", "FILL_PREPARED", "FILL_CANCELLED"]
    assert records[2]["changes_holdings"] is False
    assert records[2]["body"]["voided_fill"]["transaction_id"] == "T1"
    retried, _ = service.prepare_fill(_fill_request(idempotency_key="fill-2", expected_revision=3))
    assert retried["status"] == "FILL_PREPARED"
    assert retried["draft"]["cash_cny"] == "199995.00"


def test_cancel_without_draft_or_with_stale_digest_is_conflict(service):
    service.initialize(_initialize_request())
    with pytest.raises(JournalConflict) as error:
        service.cancel_fill({"idempotency_key": "cancel-1", "expected_revision": 1,
                             "prepared_record_sha256": "0" * 64,
                             "cancelled_at": "2026-10-12T20:30:00+08:00", "reason": "none"})
    assert error.value.code == "NO_CONFIRMABLE_DRAFT"
    _, draft_digest = service.prepare_fill(_fill_request())
    with pytest.raises(JournalConflict) as error:
        service.cancel_fill({"idempotency_key": "cancel-2", "expected_revision": 2,
                             "prepared_record_sha256": "1" * 64,
                             "cancelled_at": "2026-10-12T20:30:00+08:00", "reason": "stale"})
    assert error.value.code == "NO_CONFIRMABLE_DRAFT"
    cancelled, _ = service.cancel_fill({"idempotency_key": "cancel-3", "expected_revision": 2,
                                        "prepared_record_sha256": draft_digest,
                                        "cancelled_at": "2026-10-12T20:30:00+08:00", "reason": "ok"})
    assert cancelled["revision"] == 3


def test_cancelled_draft_cannot_be_confirmed(service):
    service.initialize(_initialize_request())
    _, draft_digest = service.prepare_fill(_fill_request())
    service.cancel_fill({"idempotency_key": "cancel-1", "expected_revision": 2,
                         "prepared_record_sha256": draft_digest,
                         "cancelled_at": "2026-10-12T20:30:00+08:00", "reason": "void"})
    with pytest.raises(JournalConflict) as error:
        service.confirm_fill({"idempotency_key": "confirm-after-cancel", "expected_revision": 3,
                              "prepared_record_sha256": draft_digest,
                              "confirmed_at": "2026-10-12T21:00:00+08:00",
                              "confirmation_note": "too late"})
    assert error.value.code == "NO_CONFIRMABLE_DRAFT"


def test_initial_holdings_can_be_reconciled_without_manufacturing_trades(service):
    service.initialize(_initialize_request())
    before = service.portfolio_view()
    request = {"idempotency_key": "reconcile-1", "expected_revision": 1,
               "reconciled_at": "2026-10-12T21:05:00+08:00", "confirmation_note": "reconciled"}
    result = service.reconcile(request)
    assert service.reconcile(request) == result
    after = service.portfolio_view()
    assert after["cash_cny"] == before["cash_cny"]
    assert after["positions"] == before["positions"]
    assert after["trades"] == []
    assert result[0]["reconciliation_scope"] == "INTERNAL_JOURNAL_REPLAY"
    assert len(service.records()) == 2


def test_rejections_are_validated_before_any_write(service):
    with pytest.raises(JournalValidationError):
        service.initialize(_initialize_request(holdings=[{"symbol": "60051", "exchange": "SSE",
                                                          "quantity": "10", "cost_basis_cny": "1"}]))
    with pytest.raises(JournalValidationError):
        service.initialize(_initialize_request(cash_cny="not-a-number"))
    with pytest.raises(JournalValidationError):
        service.initialize(_initialize_request(holdings=[{"symbol": "600519", "exchange": "SSE",
                                                          "quantity": "10.5",
                                                          "cost_basis_cny": "1"}]))
    assert service.records() == []


def test_journal_rejects_tampering_and_broken_chain(service):
    service.initialize(_initialize_request())
    service.prepare_fill(_fill_request())
    path = service.journal.path
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["body"]["cash_cny"] = "99999999.00"
    lines[0] = json.dumps(record, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(JournalValidationError):
        service.portfolio_view()


def test_journal_rejects_reordered_or_truncated_prefix(service):
    service.initialize(_initialize_request())
    service.prepare_fill(_fill_request())
    path = service.journal.path
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(lines[1] + "\n", encoding="utf-8")
    with pytest.raises(JournalValidationError):
        service.portfolio_view()


def test_journal_records_carry_no_order_and_hash_chain(service):
    service.initialize(_initialize_request())
    service.prepare_fill(_fill_request())
    records = service.records()
    assert [record["kind"] for record in records] == ["BASELINE_CONFIRMED", "FILL_PREPARED"]
    assert all(record["action"] == "no_order" for record in records)
    assert records[0]["previous_record_sha256"] is None
    assert records[1]["previous_record_sha256"] == records[0]["record_sha256"]
    assert [record["changes_holdings"] for record in records] == [True, False]
