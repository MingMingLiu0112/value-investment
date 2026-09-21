import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("historical_assumptions", ROOT / "scripts" / "build_moutai_historical_parent_equity_assumption_contract.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_contract_blocks_replay_without_dated_assumptions():
    result = MODULE.build()
    assert result["conclusion"] == "assumption_contract_registered_not_replay_eligible"
    assert result["known_before_window"]["source_published_date"] == "2014-10-30"
    assert {item["id"] for item in result["required_assumptions"]} == {
        "risk_free_rate", "beta_policy", "equity_risk_premium", "profit_and_payout_policy", "equity_bridge"}
    assert all(item["status"] == "missing" for item in result["required_assumptions"])
    assert result["formal_fair_value"] is None
    assert result["trade_approved"] is False
