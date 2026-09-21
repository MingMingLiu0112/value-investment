from decimal import Decimal

import pytest

from value_investment_agent.virtual_account import VirtualAccount
from value_investment_agent.virtual_account_store import save_checkpoint


class FakeConnection:
    def __init__(self, previous=None):
        self.previous = previous
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        return self

    def fetchone(self):
        return self.previous


def test_checkpoint_rejects_conflicting_existing_session_but_allows_exact_retry():
    entry = {"date": "2026-01-05", "nav_cny": "1000000.00"}
    account = VirtualAccount(cash=Decimal("1000000"))
    exact = FakeConnection(previous={"entry": entry})
    save_checkpoint(exact, account_id="paper-600519", symbol="600519", account=account, journal=[entry])
    assert any("INSERT INTO virtual_accounts" in query for query, _ in exact.calls)
    conflict = FakeConnection(previous={"entry": {"date": "2026-01-05", "nav_cny": "999"}})
    with pytest.raises(ValueError, match="Conflicting"):
        save_checkpoint(conflict, account_id="paper-600519", symbol="600519", account=account, journal=[entry])
