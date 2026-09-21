from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_offline_historical_runner_never_requires_a_live_quote_or_next_trade_day():
    script = (ROOT / "scripts" / "run_moutai_historical_validation.ps1").read_text(encoding="utf-8")
    assert "replay_moutai_experimental_range_strategy.py" in script
    assert "run_moutai_simulation_closure.py" in script
    assert "uses_live_quote = $false" in script
    assert "waits_for_next_trading_day = $false" in script
    assert "collect_quote_sessions.py" not in script
    assert "trade_approved = $false" in script
