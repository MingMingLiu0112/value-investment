from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json

import pytest

from value_investment_agent.domain.execution import simulation_execution_marker
from value_investment_agent.virtual_account import VirtualAccount
from value_investment_agent.virtual_account_store import load_account, save_checkpoint


class FakeConnection:
    def __init__(self, row=None):
        self.row = row
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        return self

    def fetchone(self):
        return self.row


def _persisted_state() -> dict:
    return {**VirtualAccount(cash=Decimal("1000000")).to_dict(), **simulation_execution_marker()}


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("simulation_only", None),
        ("trade_approved", None),
        ("live_eligible", None),
        ("simulation_only", False),
        ("trade_approved", True),
        ("live_eligible", True),
    ],
)
def test_load_rejects_snapshot_without_valid_simulation_marker(key, value) -> None:
    state = _persisted_state()
    if value is None:
        del state[key]
    else:
        state[key] = value

    with pytest.raises(ValueError, match=f"Simulation execution marker differs: {key}"):
        load_account(FakeConnection({"state": state}), "simulation-account")


def test_save_checkpoint_persists_marker_and_load_round_trips() -> None:
    account = VirtualAccount(cash=Decimal("123456.78"), shares=100)
    writer = FakeConnection()
    save_checkpoint(
        writer,
        account_id="simulation-account",
        symbol="600519",
        account=account,
        journal=[],
    )

    insert_query, insert_params = writer.calls[-1]
    assert "INSERT INTO virtual_accounts" in insert_query
    persisted = json.loads(insert_params[2])
    assert persisted["simulation_only"] is True
    assert persisted["trade_approved"] is False
    assert persisted["live_eligible"] is False

    restored = load_account(FakeConnection({"state": deepcopy(persisted)}), "simulation-account")
    assert restored is not None
    assert restored.to_dict() == account.to_dict()
