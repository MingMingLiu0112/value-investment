import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_pe_coverage", ROOT / "scripts" / "analyze_moutai_historical_pe_crosscheck_coverage.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_coverage_counts_each_frozen_margin_without_creating_a_signal():
    result = MODULE.analyze([{ "status": "historical_relative_pe_research_only", "price_close_cny": "60",
                              "cases": [{"scenario": "low", "conditional_value_per_share_cny": "100"},
                                        {"scenario": "mid", "conditional_value_per_share_cny": "50"},
                                        {"scenario": "high", "conditional_value_per_share_cny": "120"}]}])
    assert result["margin_condition_counts"]["low"] == {"0.20": 1, "0.30": 1, "0.40": 1}
    assert result["margin_condition_counts"]["mid"] == {"0.20": 0, "0.30": 0, "0.40": 0}
    assert result["trade_approved"] is False
