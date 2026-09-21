import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_2025_share_timeline", ROOT / "scripts" / "build_moutai_2025_share_timeline.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_2025_share_timeline_separates_contemporaneous_expectation_from_ex_post_confirmation():
    result = MODULE.build_timeline()
    expected, confirmed = result["events"]
    assert expected["known_at"].startswith("2025-08-31")
    assert expected["usable_for_2025_point_in_time_share_basis"] is True
    assert confirmed["known_at"] == "2026-04-18T00:00:00+08:00"
    assert confirmed["source"]["published_date"] == "2026-04-17"
    assert confirmed["usable_for_2025_point_in_time_share_basis"] is False
    assert result["reconciliations"]["share_delta"] == 3927585
    assert result["valuation_approved"] is False
    assert result["trade_approved"] is False
