"""PostgreSQL persistence for the research-only virtual-account contract."""
from __future__ import annotations

import json
from typing import Any

import psycopg

from .domain.execution import assert_simulation_execution, simulation_execution_marker
from .virtual_account import VirtualAccount


def _simulation_snapshot(account: VirtualAccount) -> dict[str, Any]:
    """Bind the account snapshot to the immutable simulation-only marker."""
    state = account.to_dict()
    state.update(simulation_execution_marker())
    assert_simulation_execution(state)
    return state


def load_account(connection: psycopg.Connection, account_id: str) -> VirtualAccount | None:
    row = connection.execute("SELECT state FROM virtual_accounts WHERE account_id=%s", (account_id,)).fetchone()
    if row is None:
        return None
    state = row["state"]
    assert_simulation_execution(state)
    return VirtualAccount.from_dict(state)


def save_checkpoint(connection: psycopg.Connection, *, account_id: str, symbol: str,
                    account: VirtualAccount, journal: list[dict[str, Any]]) -> None:
    """Atomically append immutable sessions and replace the matching state snapshot."""
    if not account_id or not symbol:
        raise ValueError("Account ID and symbol are required")
    connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"virtual-account:{account_id}",))
    for entry in journal:
        session_date = entry.get("date")
        if not isinstance(session_date, str):
            raise ValueError("Every journal entry requires a session date")
        previous = connection.execute(
            "SELECT entry FROM virtual_account_journal WHERE account_id=%s AND session_date=%s",
            (account_id, session_date),
        ).fetchone()
        if previous is not None:
            if previous["entry"] != entry:
                raise ValueError(f"Conflicting virtual-account journal retry for {session_date}")
            continue
        connection.execute(
            "INSERT INTO virtual_account_journal(account_id, session_date, entry) VALUES (%s, %s, %s::jsonb)",
            (account_id, session_date, json.dumps(entry, ensure_ascii=False)),
        )
    connection.execute(
        """INSERT INTO virtual_accounts(account_id, symbol, state, updated_at)
           VALUES (%s, %s, %s::jsonb, clock_timestamp())
           ON CONFLICT (account_id) DO UPDATE SET symbol=EXCLUDED.symbol,
             state=EXCLUDED.state, updated_at=EXCLUDED.updated_at""",
        (account_id, symbol, json.dumps(_simulation_snapshot(account), ensure_ascii=False)),
    )
