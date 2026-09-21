import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "moutai_historical_parent_equity_window",
    ROOT / "scripts" / "register_moutai_historical_parent_equity_window.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_parent_equity_window_is_fixed_before_assumptions_or_replay():
    result = module.build()
    assert result["window"]["start"] == "2015-01-05"
    assert result["window"]["sessions"] == 20
    assert result["frozen_starting_facts"]["source_id"] == "cninfo:1200354286"
    assert result["frozen_starting_facts"]["available_at"] <= result["information_cutoff"]
    assert result["price_or_return_outcomes_read"] is False
    assert result["model_contract_frozen"] is False
    assert result["formal_fair_value"] is None
    assert result["historical_trade_backtest_complete"] is False
