import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_historical_window_blocker_map", ROOT / "scripts" / "map_moutai_historical_window_blockers.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_registered_narrow_window_waives_no_historical_admission_gate():
    result = MODULE.build()
    assert result["window"]["start"] == "2015-01-05"
    assert result["window"]["end"] == "2015-01-30"
    assert result["input_scope"]["annual_source_id"] == "cninfo:63720184"
    assert result["input_scope"]["available_at"] <= result["input_scope"]["first_decision_at"]
    assert result["no_cash_action_within_window"]["verified"] is True
    assert result["no_cash_action_within_window"]["reviewed_action_dates"] == []
    assert all(item["material_to_window"] and not item["waived"] for item in result["blocker_mapping"])
    assert result["additional_model_fact"]["blocker"] == "prior_annual_operating_nwc_incomplete"
    assert result["additional_model_fact"]["comparative_evidence_complete"] is False
    assert result["additional_model_fact"]["unresolved_fields"] == ["notes_payable"]
    assert result["formal_fair_value"] is None
    assert result["valuation_approved"] is False
    assert result["historical_trade_backtest_complete"] is False
    assert result["trade_approved"] is False
    assert result["live_eligible"] is False
