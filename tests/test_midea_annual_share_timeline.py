import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "midea_annual_share_timeline", ROOT / "scripts" / "build_midea_annual_share_timeline.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_annual_reported_share_timeline_is_continuous_but_not_a_daily_float():
    result = MODULE.build_timeline()
    assert len(result["rows"]) == 11
    assert result["rows"][0]["closing_reported_total_shares"] == 4215808472
    assert result["rows"][-1]["closing_reported_total_shares"] == 7655955883
    assert result["reconciliations"]["annual_opening_to_prior_closing_continuous"] is True
    assert result["share_timeline_approved"] is False
    assert result["valuation_approved"] is False
