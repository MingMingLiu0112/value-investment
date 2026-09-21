import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_related_transactions", ROOT / "scripts" / "check_moutai_daily_related_transactions.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_daily_related_transaction_notice_is_a_forecast_scope_evidence_not_cost_allocation():
    result = MODULE.build_evidence()
    assert result["total_cny_100million"] == "92.06"
    assert "excluding issuer" in result["counterparty_scope"]
    assert result["scope_approved"] is False
    assert result["trade_approved"] is False
