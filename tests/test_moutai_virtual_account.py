import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_virtual", ROOT / "scripts" / "run_moutai_virtual_account.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_synthetic_execution_path_is_explicitly_not_a_backtest():
    sessions, decisions = MODULE.synthetic_inputs()
    assert len(sessions) == 5
    assert set(decisions) == {"2026-01-05", "2026-01-06"}
    assert all(key.startswith("synthetic-") for row in decisions.values() for key in [row["decision_id"]])
    assert decisions["2026-01-05"]["state"] == "proposed_entry"
    assert decisions["2026-01-05"]["quantity"] == 300
    assert decisions["2026-01-06"]["state"] == "proposed_reduce"
    assert decisions["2026-01-06"]["quantity"] == 100


def test_bounded_fixture_runs_the_existing_signal_sizing_and_ledger_chain():
    from value_investment_agent.virtual_account import replay, VirtualAccount
    sessions, decisions = MODULE.synthetic_inputs(bounded_orders=True)
    account, journal = replay(sessions, decisions)
    fills = [row["fill"] for row in journal if row["fill"]]
    assert [row["price"] for row in fills] == ["100.10", "119.88"]
    assert [row["side"] for row in fills] == ["buy", "sell"]
    assert all(row["execution_scope"] == "daily_simulation_assumption_not_real_fill" for row in fills)
    restored = VirtualAccount.from_dict(account.to_dict())
    assert replay(sessions, decisions, restored)[1] == []
    assert restored.to_dict() == account.to_dict()
