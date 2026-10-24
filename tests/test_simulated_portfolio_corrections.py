"""SIM-only append corrections; original bytes, reasons and identities survive."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_simulated_portfolio_service_v1 import factory, initialize, fill, entry, source, now
from value_investment_agent.application.portfolio.private_portfolio_service import (
    PrivateJournal, PrivatePortfolioService, JournalValidationError, JournalConflict,
)
from value_investment_agent.application.portfolio.simulated_portfolio_service_v1 import (
    CORRECTION_KIND, SimulatedCorrectionJournal,
)


def journal(root, name="paper-a"):
    return root / "runtime/simulated-portfolios-v1" / name / "journal.jsonl"


def request(service, target, changes, *, version=None, key="correct"):
    return dict(confirmed_hypothetical=True, idempotency_key=key,
        expected_revision=service.read()["revision"], target_fill_record_sha256=target,
        expected_original_version=version or target, changes=changes, confirmed_at=now(),
        reason="Explicit human correction of hypothetical fill, not another trade")


def setup(root, quantity="200", second="100", sold="100"):
    service = factory(root, sources={"core": source(root)})
    initialize(service)
    _, a = fill(service, "A", quantity=quantity)
    entry(service, a)
    _, b = fill(service, "B", quantity=second, day="2026-10-22")
    entry(service, b)
    _, sell = fill(service, "sell", side="SELL", quantity=sold, day="2026-10-23")
    return service, a, b, sell


def test_price_fees_quantity_replay_prefix_entry_and_snapshot(tmp_path):
    service, a, b, sold = setup(tmp_path)
    service.reconcile(dict(confirmed_hypothetical=True, idempotency_key="reconcile",
        expected_revision=service.read()["revision"], reconciled_at=now(), confirmation_note="Internal SIM"))
    original = journal(tmp_path).read_bytes()
    original_hash = sha256(original).hexdigest()
    old = service.read()
    payload = request(service, a, dict(price_cny="12", fees_cny="7", quantity="100"))
    response, version = service.correct_confirmed_fill(payload)
    assert service.correct_confirmed_fill(payload) == (response, version)
    after_bytes = journal(tmp_path).read_bytes()
    assert after_bytes.startswith(original) and sha256(after_bytes[:len(original)]).hexdigest() == original_hash
    records = SimulatedCorrectionJournal(journal(tmp_path)).read()
    assert len(records) == old["revision"] + 1
    assert records[-1]["kind"] == CORRECTION_KIND
    assert sum(r["kind"] == "FILL_CONFIRMED" for r in records) == 3
    view = service.read()
    assert view["portfolio"]["cash_cny"] == "8783"
    assert view["portfolio"]["realized_pnl_cny"] == "-212"
    assert view["portfolio"]["latest_snapshot"] is None
    assert view["portfolio"]["reconciliation"]["status"] != "RECONCILED"
    assert view["correction_reconciliation_status"] == "INVALIDATED_RECONCILIATION_REQUIRED"
    first = view["entries"][0]
    assert first["hypothesis"] == old["entries"][0]["hypothesis"]
    assert first["entry_confirmation_sha256"] == old["entries"][0]["entry_confirmation_sha256"]
    assert first["fill_correction"]["original_fill"]["quantity"] == "200"
    assert first["fill_correction"]["effective_fill"]["quantity"] == "100"
    assert first["remaining_quantity"] == "0" and first["advisory_eligible"] is False
    assert view["entries"][1]["remaining_quantity"] == "100"
    assert factory(tmp_path).read() == view
    consumption = service.entry_consumption(sell_fill_sha256=sold)
    assert consumption["consumed_entry_fill_sha256"] == [a]
    service.reconcile(dict(confirmed_hypothetical=True, idempotency_key="reconcile-new",
        expected_revision=view["revision"], reconciled_at=now(), confirmation_note="Corrected internal SIM"))
    assert service.read()["correction_reconciliation_status"] == "RECONCILED_AFTER_CORRECTION"
    assert service.read()["risk_snapshot"]["namespace"] == "SIMULATED"
    fill(service, "later", quantity="100", day="2026-10-23")
    assert service.read()["correction_reconciliation_status"] == "INVALIDATED_RECONCILIATION_REQUIRED"


def test_fifo_distribution_recomputed_not_client_entry_choice(tmp_path):
    service, a, b, sold = setup(tmp_path, second="200", sold="250")
    assert service.read()["entries"][1]["remaining_quantity"] == "150"
    service.correct_confirmed_fill(request(service, a, {"quantity": "100"}))
    view = service.read()
    assert view["entries"][1]["remaining_quantity"] == "50"
    consumed = service.entry_consumption(sell_fill_sha256=sold)
    assert consumed["consumed_entry_fill_sha256"] == [a, b]
    assert consumed["before"][b]["remaining_quantity"] == "200"
    assert consumed["after"][b]["remaining_quantity"] == "50"


def test_sell_price_quantity_fees_restate_realized_pnl_and_fifo(tmp_path):
    service, a, b, sold = setup(tmp_path)
    service.correct_confirmed_fill(request(service, sold, {"quantity": "200", "price_cny": "11", "fees_cny": "3"}))
    view = service.read()
    assert view["portfolio"]["cash_cny"] == "9187"
    assert view["portfolio"]["realized_pnl_cny"] == "192"
    assert view["entries"][0]["remaining_quantity"] == "0"
    assert view["entries"][1]["remaining_quantity"] == "100"
    assert service.entry_consumption(sell_fill_sha256=sold)["consumed_entry_fill_sha256"] == [a]


def test_illegal_partial_fifo_successor_rejects_without_write(tmp_path):
    service, a, _, _ = setup(tmp_path, sold="250")
    before = journal(tmp_path).read_bytes()
    with pytest.raises(JournalValidationError, match="sellable"):
        service.correct_confirmed_fill(request(service, a, {"quantity": "100"}))
    assert journal(tmp_path).read_bytes() == before


def test_older_lot_correction_cannot_sell_new_same_day_lots(tmp_path):
    service = factory(tmp_path)
    initialize(service)
    _, a = fill(service, "old", quantity="200")
    fill(service, "new", quantity="200", day="2026-10-22")
    fill(service, "sell", side="SELL", quantity="200", day="2026-10-22")
    before = journal(tmp_path).read_bytes()
    # Total shares suffice after correction, but the extra same-day lot is T+1 locked.
    with pytest.raises(JournalValidationError, match="sellable"):
        service.correct_confirmed_fill(request(service, a, {"quantity": "100"}))
    assert journal(tmp_path).read_bytes() == before


@pytest.mark.parametrize("changes", [{"quantity": "0"}, {"quantity": "150"},
    {"fees_cny": "-1"}, {"price_cny": "0"}, {"price_cny": "NaN"}])
def test_invalid_corrected_numbers_do_not_append(tmp_path, changes):
    service = factory(tmp_path)
    initialize(service)
    _, a = fill(service, "A")
    before = journal(tmp_path).read_bytes()
    with pytest.raises(JournalValidationError):
        service.correct_confirmed_fill(request(service, a, changes))
    assert journal(tmp_path).read_bytes() == before


def test_explicit_confirmation_is_required(tmp_path):
    service = factory(tmp_path)
    initialize(service)
    _, a = fill(service, "A")
    before = journal(tmp_path).read_bytes()
    with pytest.raises(JournalValidationError, match="confirmation"):
        service.correct_confirmed_fill(dict(request(service, a, {"fees_cny": "6"}), confirmed_hypothetical=False))
    assert journal(tmp_path).read_bytes() == before


@pytest.mark.parametrize("field,value", [("side", "SELL"), ("sleeve", "HOTSPOT_SATELLITE"),
    ("symbol", "300750"), ("trade_date", "2026-10-22"), ("next_sell_session", "2026-10-21")])
def test_cannot_change_identity_or_sellable_day(tmp_path, field, value):
    service, a, _, _ = setup(tmp_path)
    before = journal(tmp_path).read_bytes()
    with pytest.raises(JournalValidationError, match="Only price"):
        service.correct_confirmed_fill(request(service, a, {field: value}))
    assert journal(tmp_path).read_bytes() == before


def test_original_version_revision_idempotency_and_cross_account(tmp_path):
    service, a, _, _ = setup(tmp_path)
    payload = request(service, a, {"fees_cny": "9"})
    first = service.correct_confirmed_fill(payload)
    before = journal(tmp_path).read_bytes()
    assert service.correct_confirmed_fill(payload) == first
    with pytest.raises(JournalConflict):
        service.correct_confirmed_fill(dict(payload, changes={"fees_cny": "10"}))
    with pytest.raises(JournalValidationError, match="version mismatch"):
        service.correct_confirmed_fill(request(service, a, {"fees_cny": "11"}, key="stale"))
    stale = request(service, a, {"fees_cny": "11"}, version=first[1], key="revision")
    with pytest.raises(JournalConflict, match="revision"):
        service.correct_confirmed_fill(dict(stale, expected_revision=1))
    assert journal(tmp_path).read_bytes() == before
    second = service.correct_confirmed_fill(request(service, a, {"fees_cny": "11"}, version=first[1], key="v2"))
    assert second[1] != first[1]
    other = factory(tmp_path, "paper-b")
    initialize(other)
    original_other = journal(tmp_path, "paper-b").read_bytes()
    with pytest.raises(JournalValidationError, match="version mismatch"):
        other.correct_confirmed_fill(request(other, a, {"fees_cny": "1"}))
    assert journal(tmp_path, "paper-b").read_bytes() == original_other


def test_actual_and_old_journal_validator_reject_new_kind(tmp_path):
    service, a, _, _ = setup(tmp_path)
    service.correct_confirmed_fill(request(service, a, {"fees_cny": "6"}))
    with pytest.raises(JournalValidationError):
        PrivateJournal(journal(tmp_path)).read()
    with pytest.raises(JournalValidationError):
        PrivatePortfolioService(PrivateJournal(journal(tmp_path))).records()
    last = SimulatedCorrectionJournal(journal(tmp_path)).read()[-1]
    with pytest.raises(JournalValidationError):
        PrivateJournal._validate_record(last, line_number=last["sequence"], previous=last["previous_record_sha256"])


@pytest.mark.parametrize("price", ["60", "85"])
def test_historical_sleeve_and_shared_reserve_revalidated(tmp_path, price):
    from datetime import date
    from value_investment_agent.application.portfolio.simulated_trade_journey import _policy
    service = factory(tmp_path)
    initialize(service)
    _, digest = service.prepare_policy(dict(confirmed_hypothetical=True, idempotency_key="ips",
        expected_revision=1, policy=_policy(date(2026, 10, 20))))
    service.confirm_policy(dict(confirmed_hypothetical=True, idempotency_key="ips-ok",
        expected_revision=2, prepared_record_sha256=digest, confirmed_at=now(), confirmation_note="Hypothetical IPS"))
    _, a = fill(service, "A")
    before = journal(tmp_path).read_bytes()
    with pytest.raises(JournalValidationError, match="budget"):
        service.correct_confirmed_fill(request(service, a, {"price_cny": price}))
    assert journal(tmp_path).read_bytes() == before


def test_later_sale_cannot_hide_intermediate_sleeve_budget_breach(tmp_path):
    from datetime import date
    from value_investment_agent.application.portfolio.simulated_trade_journey import _policy
    service = factory(tmp_path)
    initialize(service)
    _, policy_hash = service.prepare_policy(dict(confirmed_hypothetical=True, idempotency_key="ips",
        expected_revision=1, policy=_policy(date(2026, 10, 20))))
    service.confirm_policy(dict(confirmed_hypothetical=True, idempotency_key="ips-ok",
        expected_revision=2, prepared_record_sha256=policy_hash, confirmed_at=now(), confirmation_note="SIM IPS"))
    _, a = fill(service, "A")
    fill(service, "sold-later", side="SELL", day="2026-10-22")
    before = journal(tmp_path).read_bytes()
    # Final core cash would be positive after sale; the historical BUY was not funded by its sleeve.
    with pytest.raises(JournalValidationError, match="budget"):
        service.correct_confirmed_fill(request(service, a, {"price_cny": "60"}))
    assert journal(tmp_path).read_bytes() == before


def test_pending_draft_blocks_correction(tmp_path):
    service, a, _, _ = setup(tmp_path)
    _, _ = service.prepare_fill(dict(confirmed_hypothetical=True, idempotency_key="draft",
        expected_revision=service.read()["revision"], fill=dict(transaction_id="pending", side="BUY",
        sleeve="CORE_VALUE", symbol="600519", exchange="SSE", quantity="100", price_cny="10",
        fees_cny="5", trade_date="2026-10-23", next_sell_session="2026-10-26", trading_unit="100")))
    before = journal(tmp_path).read_bytes()
    with pytest.raises(JournalValidationError, match="drafts"):
        service.correct_confirmed_fill(request(service, a, {"fees_cny": "10"}))
    assert journal(tmp_path).read_bytes() == before


def test_new_process_restores_effective_history_and_original_entry(tmp_path):
    service, a, _, sold = setup(tmp_path)
    service.correct_confirmed_fill(request(service, a, {"quantity": "100", "price_cny": "12", "fees_cny": "7"}))
    expected = service.read()
    code = """import json,sys; from pathlib import Path
from value_investment_agent.application.portfolio.simulated_portfolio_service_v1 import create_simulated_portfolio_service
s=create_simulated_portfolio_service(repository_root=Path(sys.argv[1]),account_id='paper-a')
print(json.dumps(s.read()))
"""
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"), PYTHONDONTWRITEBYTECODE="1")
    actual = json.loads(subprocess.check_output([sys.executable, "-B", "-c", code, str(tmp_path)],
        env=env, text=True, encoding="utf-8"))
    assert actual == expected
