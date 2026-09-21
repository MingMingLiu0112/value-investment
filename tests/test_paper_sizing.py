from decimal import Decimal

from value_investment_agent.paper_sizing import size_entry_or_add, size_one_third_reduce
from value_investment_agent.virtual_account import replay


def test_registered_tranches_respect_cap_cash_fee_and_board_lot():
    entry = size_entry_or_add(nav=Decimal("1000000"), cash=Decimal("1000000"),
                              current_shares=0, price=Decimal("100"), tranche_index=0)
    assert Decimal(entry["registered_tranche_budget_cny"]) == Decimal("40000.00")
    assert entry["quantity"] == 300
    first_add = size_entry_or_add(nav=Decimal("1000000"), cash=Decimal("1000000"),
                                  current_shares=300, price=Decimal("100"), tranche_index=1)
    assert first_add["quantity"] == 200
    second_add = size_entry_or_add(nav=Decimal("1000000"), cash=Decimal("1000000"),
                                   current_shares=500, price=Decimal("100"), tranche_index=2)
    assert second_add["quantity"] == 100


def test_sizing_never_exceeds_cap_or_invents_a_partial_reduce():
    capped = size_entry_or_add(nav=Decimal("1000000"), cash=Decimal("1000000"),
                               current_shares=800, price=Decimal("100"), tranche_index=2)
    assert capped["quantity"] == 0
    assert "position_cap_reached" in capped["reasons"]
    assert size_one_third_reduce(sellable_shares=900)["quantity"] == 300
    small = size_one_third_reduce(sellable_shares=200)
    assert small["quantity"] == 0
    assert small["reasons"] == ["partial_reduce_below_board_lot"]


def test_sized_entry_flows_to_next_session_paper_fill_within_cap():
    proposal = size_entry_or_add(nav=Decimal("1000000"), cash=Decimal("1000000"),
                                 current_shares=0, price=Decimal("100"), tranche_index=0)
    account, journal = replay(
        [{"date": "2026-01-05", "open": "100", "close": "100", "execution_ready": True},
         {"date": "2026-01-06", "open": "100", "close": "100", "execution_ready": True}],
        {"2026-01-05": {"state": "proposed_entry", "decision_id": "sized-entry",
                          "quantity": proposal["quantity"]}},
    )
    assert journal[1]["fill"]["quantity"] == proposal["quantity"]
    assert Decimal(account.shares) * Decimal("100") <= Decimal("1000000") * Decimal("0.08")
