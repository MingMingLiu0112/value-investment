import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_2025_finance_reconciliation", ROOT / "scripts" / "reconcile_moutai_2025_finance_transactions.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_related_party_schedule_reconciles_to_consolidated_comparator_only_within_rounding():
    result = MODULE.build_reconciliation()
    assert result["schedule"]["closing_cny"] == "18038383700.00"
    assert result["annual_comparator"]["opening_cny"] == "18038383776.30"
    assert result["reconciliation"]["difference_cny"] == "76.30"
    assert result["reconciliation"]["within_rounding"] is True
    assert result["scope_approved"] is False
