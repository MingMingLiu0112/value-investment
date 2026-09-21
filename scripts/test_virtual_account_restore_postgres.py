#!/usr/bin/env python3
"""Exercise virtual-account persistence only against the configured restore DB."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from value_investment_agent.db import connect, initialize
from value_investment_agent.settings import get_settings
from value_investment_agent.virtual_account import VirtualAccount
from value_investment_agent.virtual_account_store import load_account, save_checkpoint


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_ID = "isolated-test-600519"


def main() -> int:
    settings = get_settings()
    if not settings.restore_database_url or settings.restore_database_url == settings.database_url:
        raise RuntimeError("A distinct RESTORE_DATABASE_URL is required")
    initialize(settings.restore_database_url, ROOT / "sql" / "001_init.sql")
    account = VirtualAccount(cash=Decimal("1000000"))
    journal = [{"date": "2026-01-05", "nav_cny": "1000000.00", "decision": "isolated_test_only"}]
    with connect(settings.restore_database_url) as connection:
        save_checkpoint(connection, account_id=ACCOUNT_ID, symbol="600519", account=account, journal=journal)
        connection.commit()
        restored = load_account(connection, ACCOUNT_ID)
        if restored is None or restored.to_dict() != account.to_dict():
            raise ValueError("Restore database returned a different virtual-account snapshot")
        save_checkpoint(connection, account_id=ACCOUNT_ID, symbol="600519", account=account, journal=journal)
        connection.commit()
        count = connection.execute(
            "SELECT count(*) AS count FROM virtual_account_journal WHERE account_id=%s", (ACCOUNT_ID,)
        ).fetchone()["count"]
        if count != 1:
            raise ValueError("Idempotent checkpoint created duplicate journal entries")
    print({"isolated_postgres_virtual_account": "passed", "journal_rows": count, "production_touched": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
