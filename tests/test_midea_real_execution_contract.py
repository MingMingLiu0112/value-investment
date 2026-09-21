import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("midea_real_contract", ROOT / "scripts" / "build_midea_real_execution_contract.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_contract_preserves_suspension_boundaries_and_blocks_partial_day():
    contract = MODULE.build_contract()
    dates = {row["date"] for row in contract["sessions"]}
    assert contract["symbol"] == "000333"
    assert len(contract["full_day_suspensions"]) == 5
    for event in contract["full_day_suspensions"]:
        assert event["resume_date"] in dates
        assert not any(event["start_date"] <= day < event["resume_date"] for day in dates)
    partial = next(row for row in contract["sessions"] if row["date"] == "2016-06-16")
    assert partial["execution_status"] == "blocked_daily_bar_contains_partial_session_suspension"
    assert contract["decisions"] == {}
    assert contract["trade_approved"] is False


def test_full_day_bar_conflict_fails():
    with pytest.raises(ValueError, match="conflicts with full-day suspension"):
        MODULE.apply_constraints(
            [{"date": "2018-09-10", "open": "1", "close": "1"}, {"date": "2016-06-16", "open": "1", "close": "1"}],
            [{"start_date": "2018-09-10", "resume_date": "2018-10-29"}],
            {},
        )
