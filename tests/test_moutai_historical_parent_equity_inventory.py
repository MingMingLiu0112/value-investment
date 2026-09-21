import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "moutai_historical_parent_equity_inventory",
    ROOT / "scripts" / "build_moutai_historical_parent_equity_inventory.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_registered_window_uses_verified_parent_equity_fact_without_promoting_a_value():
    result = module.build()
    fact = result["annual_parent_equity_fact"]
    assert result["window"]["start"] == "2015-01-05"
    assert fact["source_id"] == "cninfo:63720184"
    assert fact["available_at"] <= result["decision_information_cutoff"]
    assert fact["parent_equity_cny"] == "42622216487.81"
    assert fact["parent_profit_cny"] == "15136639784.35"
    assert fact["reported_ending_issued_shares"] == "1038180000"
    assert result["intervening_capital_and_distribution_context"]["issued_shares_after_2014_bonus_event"] == "1141998000.00000"
    assert result["formal_fair_value"] is None
    assert result["valuation_approved"] is False
    assert result["historical_trade_backtest_complete"] is False
    assert result["trade_approved"] is False
