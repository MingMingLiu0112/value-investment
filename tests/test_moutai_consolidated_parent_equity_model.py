import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_parent_equity_model", ROOT / "scripts" / "assess_moutai_consolidated_equity_model.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_scope_matched_candidate_stays_outside_admission():
    result = MODULE.build()
    assert result["candidate_model"]["name"] == "consolidated_parent_equity_residual_income_or_dividend_capacity"
    assert result["scope_findings"]["industrial_finance_carveout_required"] is False
    assert result["scope_findings"]["enterprise_to_equity_bridge_required"] is False
    assert result["conclusion"] == "candidate_scope_matched_but_not_admitted"
    assert result["valuation_approved"] is False
    assert result["simulation_eligible"] is False
    assert result["trade_approved"] is False
