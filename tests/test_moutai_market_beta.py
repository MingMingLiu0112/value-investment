import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_market_beta", ROOT / "scripts" / "research_moutai_market_beta.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_market_slope_reports_descriptive_uncertainty():
    rows = [
        {"market_return": "-0.02", "stock_return": "-0.01"},
        {"market_return": "0.00", "stock_return": "0.01"},
        {"market_return": "0.02", "stock_return": "0.03"},
    ]
    result = MODULE.estimate_market_slope(rows)
    assert result["equity_return_slope"] == 1.0
    assert result["ols_slope_standard_error_iid_assumption"] < 1e-12
    low, high = result["approximate_95pct_slope_interval_iid_assumption"]
    assert abs(low - 1.0) < 1e-12
    assert abs(high - 1.0) < 1e-12
