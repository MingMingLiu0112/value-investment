import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_finance_extract", ROOT / "scripts" / "extract_moutai_finance_transaction_note.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_scanned_transaction_table_is_reconciled_but_not_promoted_to_valuation():
    evidence = MODULE.build_evidence()
    assert len(evidence["rows"]) == 6
    assert evidence["derived"]["related_party_deposit_closing_cny"] == "17970538500.00"
    assert evidence["not_used_for_valuation"] is True
    assert evidence["scope_approved"] is False
    assert evidence["trade_approved"] is False
