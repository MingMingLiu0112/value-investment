import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "midea_2025_share_scope", ROOT / "scripts" / "reconcile_midea_2025_share_scope.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_annual_and_monthly_share_facts_reconcile_without_forward_fill():
    result = MODULE.build_reconciliation()
    assert result["annual_to_monthly_issued_total_delta"] == 26905661
    assert result["monthly_issued_total_shares"] - result["monthly_treasury_total_shares"] == 7584272700
    assert result["share_scope_approved"] is False
    assert result["valuation_approved"] is False
