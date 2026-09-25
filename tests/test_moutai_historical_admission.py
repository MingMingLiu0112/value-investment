import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_admission", ROOT / "scripts" / "audit_moutai_historical_admission.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_audit_does_not_treat_research_inputs_as_approved_historical_values():
    rows = json.loads(MODULE.INPUT.read_text(encoding="utf-8"))
    result = MODULE.audit(rows)
    assert result["sessions"] == 2674
    assert result["historical_value"]["present_sessions"] == 0
    assert result["historical_value"]["approved_sessions"] == 0
    assert result["admission"]["historical_trade_backtest_complete"] is False
    assert result["admission"]["validation_classification"] == "NOT_PIT_SAFE"
    assert result["admission"]["validation_admission_status"] == "NOT_ADMITTED"
    assert result["admission"]["performance_claim_allowed"] is False
    assert result["blocker_counts"]["historical_valuation_not_approved"] == 2674
    capital = result["capital_and_distribution"]
    assert capital["sessions_with_disclosed_repurchase_snapshot"] + capital["sessions_without_disclosed_repurchase_snapshot"] == capital["sessions_after_2025_repurchase_program_start"]
