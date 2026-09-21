import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_post_fee_window", ROOT / "scripts" / "preregister_moutai_post_fee_window.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_post_fee_window_is_mechanically_selected_and_not_a_backtest():
    result = MODULE.build()
    assert result["window"]["start"] == "2015-08-03"
    assert result["window"]["end"] == "2015-08-28"
    assert result["window"]["sessions"] == 20
    assert result["window"]["annual_source_id"] == "cninfo:1200877315"
    assert result["excluded_reviewed_cash_action_dates"] == []
    assert result["historical_trade_backtest_complete"] is False
    assert result["trade_approved"] is False
