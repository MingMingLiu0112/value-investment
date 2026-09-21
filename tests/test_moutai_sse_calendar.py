import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_sse_calendar", ROOT / "scripts" / "audit_moutai_sse_calendar.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_sse_calendar_matches_pinned_bar_dates_but_not_execution():
    audit = MODULE.build_audit()
    assert audit["calendar_approved"] is True
    assert audit["execution_approved"] is False
    assert audit["sse_open_dates"] == 2674
    assert audit["missing_from_moutai"] == []
    assert audit["extra_moutai_dates"] == []


def test_amendments_override_original_calendar_dates():
    dates = MODULE.expected_open_dates()
    assert "2019-05-02" not in dates
    assert "2019-05-06" in dates
    assert "2020-01-31" not in dates
    assert "2020-02-03" in dates
    assert "2015-09-03" not in dates
    assert "2018-12-31" not in dates
