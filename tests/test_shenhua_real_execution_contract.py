import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("shenhua_real_contract", ROOT / "scripts" / "build_shenhua_real_execution_contract.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_contract_excludes_reviewed_suspensions_and_preserves_resumption_bars():
    contract = MODULE.build_contract()
    dates = {row["date"] for row in contract["sessions"]}
    assert contract["symbol"] == "601088"
    assert len(contract["full_day_suspensions"]) == 2
    for event in contract["full_day_suspensions"]:
        assert event["resumes_at_open"] in dates
        assert not any(event["suspended_from_inclusive"] <= day < event["resumes_at_open"] for day in dates)
    assert contract["cash_distribution_scope"]["backtest_ready"] is False
    assert contract["cash_distribution_scope"]["treatment"] == "not_applied_to_returns"
    assert contract["decisions"] == {}
    assert contract["trade_approved"] is False


def test_suspension_bar_conflict_fails():
    with pytest.raises(ValueError, match="conflicts with official suspension"):
        original = MODULE.load_bars
        try:
            MODULE.load_bars = lambda: ([{"date": "2017-06-05", "open": "1", "close": "1"}], [])
            MODULE.build_contract()
        finally:
            MODULE.load_bars = original
