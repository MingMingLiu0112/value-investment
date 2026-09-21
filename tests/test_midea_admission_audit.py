import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("midea_admission", ROOT / "scripts" / "audit_midea_admission.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_midea_can_be_watched_but_cannot_produce_a_per_share_order():
    result = MODULE.build_audit()
    assert result["research_state"] == "watch"
    assert result["action"] == "no_order"
    assert result["facts"]["execution_sessions"] == 2621
    assert result["blocking_gate_ids"] == ["financial_scope", "per_share_scope", "formal_valuation"]
    assert result["trade_approved"] is False
