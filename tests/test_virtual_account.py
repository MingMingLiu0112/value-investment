from decimal import Decimal
from datetime import date

from value_investment_agent.virtual_account import VirtualAccount, dated_research_fee, replay


SESSIONS = [
    {"date": "2026-01-05", "open": "100", "close": "100"},
    {"date": "2026-01-06", "open": "100", "close": "102"},
    {"date": "2026-01-07", "open": "103", "close": "101"},
    {"date": "2026-01-08", "open": "99", "close": "99"},
]


def test_entry_then_reduce_uses_next_open_and_t1_cash_ledger():
    decisions = {
        "2026-01-05": {"decision_id": "entry-1", "state": "proposed_entry", "quantity": 100},
        "2026-01-06": {"decision_id": "exit-1", "state": "proposed_exit", "quantity": 100},
    }
    account, journal = replay(SESSIONS, decisions, VirtualAccount(cash=Decimal("1000000")))
    assert journal[0]["pending_order_id"] == "entry-1"
    assert journal[1]["fill"]["price"] == "100"
    assert journal[1]["holding_shares"] == 100
    assert journal[2]["fill"]["price"] == "103"
    assert account.shares == 0
    assert account.cash > Decimal("1000000")


def test_replay_with_same_account_does_not_duplicate_completed_order():
    decisions = {"2026-01-05": {"decision_id": "entry-1", "state": "proposed_entry", "quantity": 100}}
    account, first = replay(SESSIONS[:2], decisions)
    _, second = replay(SESSIONS[:2], decisions, account)
    assert first[1]["fill"]["order_id"] == "entry-1"
    assert second == []
    assert account.shares == 100


def test_replay_processes_only_new_sessions_and_fills_a_pending_order_once():
    decisions = {"2026-01-05": {"decision_id": "entry-1", "state": "proposed_entry", "quantity": 100}}
    account, first = replay(SESSIONS[:1], decisions)
    assert first[0]["pending_order_id"] == "entry-1"
    account, second = replay(SESSIONS[:2], decisions, account)
    assert len(second) == 1
    assert second[0]["fill"]["order_id"] == "entry-1"
    assert account.processed_sessions == {"2026-01-05", "2026-01-06"}


def test_json_snapshot_restores_the_same_idempotent_account_state():
    decisions = {"2026-01-05": {"decision_id": "entry-1", "state": "proposed_entry", "quantity": 100}}
    account, _ = replay(SESSIONS[:2], decisions)
    restored = VirtualAccount.from_dict(account.to_dict())
    _, replayed = replay(SESSIONS[:2], decisions, restored)
    assert replayed == []
    assert restored.marked_nav() == account.marked_nav()


def test_oversized_sell_is_rejected_without_short_position():
    account = VirtualAccount(cash=Decimal("1000000"), shares=100)
    account.lots = [(date(2026, 1, 2), 100)]
    decisions = {"2026-01-05": {"decision_id": "exit-1", "state": "proposed_exit", "quantity": 200}}
    _, journal = replay(SESSIONS[:2], decisions, account)
    assert journal[1]["rejected_order_reason"] == "insufficient_t1_sellable_shares"
    assert journal[1]["holding_shares"] == 100


def test_reduce_without_an_explicit_sized_quantity_never_defaults_to_full_exit():
    account = VirtualAccount(cash=Decimal("1000000"), shares=100)
    account.lots = [(date(2026, 1, 2), 100)]
    decisions = {"2026-01-05": {"decision_id": "reduce-unsized", "state": "proposed_reduce"}}
    account, journal = replay(SESSIONS[:2], decisions, account)
    assert journal[1]["fill"] is None
    assert journal[1]["rejected_order_reason"] == "reduce_quantity_required"
    assert account.shares == 100


def test_cash_distribution_uses_record_date_shares_and_payment_date_cash():
    account = VirtualAccount(cash=Decimal("1000000"), shares=100)
    account.lots = [(date(2026, 1, 2), 100)]
    events = [{"event_id": "div-1", "record_date": "2026-01-05", "ex_date": "2026-01-06",
               "payment_date": "2026-01-07", "cash_per_share": "2.50"}]
    _, journal = replay(SESSIONS[:3], {}, account, cash_events=events)
    assert journal[0]["cash_events"] == [{"event_id": "div-1", "kind": "record", "shares": 100}]
    assert journal[1]["receivable_cny"] == "250.00"
    assert journal[2]["cash_cny"] == "1000250.00"
    assert journal[2]["receivable_cny"] == "0.00"


def test_same_day_ex_and_payment_are_applied_once_each():
    account = VirtualAccount(cash=Decimal("1000000"), shares=100)
    account.lots = [(date(2026, 1, 2), 100)]
    events = [{"event_id": "div-1", "record_date": "2026-01-05", "ex_date": "2026-01-06",
               "payment_date": "2026-01-06", "cash_per_share": "2.50"}]
    _, journal = replay(SESSIONS[:2], {}, account, cash_events=events)
    assert journal[1]["cash_events"] == [
        {"event_id": "div-1", "kind": "accrual", "amount_cny": "250.00"},
        {"event_id": "div-1", "kind": "payment", "amount_cny": "250.00"},
    ]
    assert journal[1]["cash_cny"] == "1000250.00"


def test_bonus_shares_are_locked_until_the_disclosed_listing_session():
    sessions = [
        {"date": "2026-01-05", "open": "100", "close": "100"},
        {"date": "2026-01-06", "open": "100", "close": "100"},
        {"date": "2026-01-07", "open": "100", "close": "100"},
        {"date": "2026-01-08", "open": "100", "close": "100"},
    ]
    account = VirtualAccount(cash=Decimal("1000000"), shares=100)
    account.lots = [(date(2026, 1, 2), 100)]
    events = [{"event_id": "bonus-1", "record_date": "2026-01-05", "ex_date": "2026-01-06",
               "payment_date": "2026-01-06", "cash_per_share": "0", "bonus_shares_per_share": "0.1",
               "bonus_listing_date": "2026-01-08"}]
    _, journal = replay(sessions, {}, account, cash_events=events)
    assert journal[1]["holding_shares"] == 110
    assert journal[1]["sellable_shares"] == 100
    assert journal[3]["sellable_shares"] == 110


def test_record_date_purchase_receives_dividend_after_snapshot_restore():
    events = [{"event_id": "div-entry", "record_date": "2026-01-06",
               "ex_date": "2026-01-07", "payment_date": "2026-01-08", "cash_per_share": "2.50"}]
    decisions = {"2026-01-05": {"decision_id": "entry", "state": "proposed_entry", "quantity": 100}}
    account, _ = replay(SESSIONS[:1], decisions)
    account = VirtualAccount.from_dict(account.to_dict())
    account, journal = replay(SESSIONS, decisions, account, cash_events=events)
    assert account.entitlement_shares["div-entry"] == 100
    assert journal[0]["cash_events"][-1]["shares"] == 100
    assert journal[1]["receivable_cny"] == "250.00"
    assert account.cash == Decimal("990245.00")
    snapshot = account.to_dict()
    account, repeated = replay(SESSIONS, decisions, account, cash_events=events)
    assert repeated == []
    assert account.to_dict() == snapshot


def test_record_date_sale_excludes_sold_shares_from_dividend():
    account = VirtualAccount(shares=200, lots=[(date(2026, 1, 2), 200)])
    events = [{"event_id": "div-sale", "record_date": "2026-01-06",
               "ex_date": "2026-01-07", "payment_date": "2026-01-08", "cash_per_share": "2.50"}]
    decisions = {"2026-01-05": {"decision_id": "reduce", "state": "proposed_reduce", "quantity": 100}}
    account, journal = replay(SESSIONS, decisions, account, cash_events=events)
    assert account.entitlement_shares["div-sale"] == 100
    assert journal[2]["receivable_cny"] == "250.00"
    assert account.cash == Decimal("1010240.00")


def test_unaffordable_automatic_buy_is_rejected_without_crashing():
    decisions = {"2026-01-05": {"decision_id": "entry", "state": "proposed_entry"}}
    account, journal = replay(SESSIONS[:2], decisions, VirtualAccount(cash=Decimal("10")))
    assert journal[1]["rejected_order_reason"] == "insufficient_cash_or_board_lot"
    assert journal[1]["fill"] is None
    assert account.cash == Decimal("10")
    assert account.shares == 0
    assert account.pending_order is None


def test_dated_research_fee_uses_pre_2023_and_current_stamp_duty_rates():
    pre_cut = dated_research_fee("sell", 100, Decimal("100"), date(2022, 1, 4))
    current = dated_research_fee("sell", 100, Decimal("100"), date(2025, 1, 4))
    assert pre_cut == Decimal("15.20")
    assert current == Decimal("10.10")


def test_replay_uses_injected_dated_fee_calculator():
    sessions = [
        {"date": "2025-01-02", "open": "100", "close": "100"},
        {"date": "2025-01-03", "open": "100", "close": "100"},
    ]
    decisions = {"2025-01-02": {"decision_id": "entry", "state": "proposed_entry", "quantity": 100}}
    _, journal = replay(sessions, decisions, fee_calculator=dated_research_fee)
    assert journal[1]["fill"]["fee_cny"] == "5.10"
