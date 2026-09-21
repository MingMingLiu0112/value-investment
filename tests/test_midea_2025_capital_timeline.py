import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "midea_2025_capital_timeline", ROOT / "scripts" / "build_midea_2025_capital_timeline.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_capital_timeline_keeps_unknown_interval_and_cancellation_separate():
    result = MODULE.build_timeline()
    assert result["known_differences"]["september_to_december_pre_cancellation_issued_total_delta"] == 9944234
    assert result["events"][1]["issued_total_before"] - result["events"][1]["issued_total_after"] == 95000000
    assert result["share_scope_approved"] is False
    assert result["trade_approved"] is False
