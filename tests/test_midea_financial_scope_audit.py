import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "midea_financial_scope", ROOT / "scripts" / "audit_midea_financial_scope.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_ttm_profit_remains_available_while_eps_and_trade_are_blocked():
    result = MODULE.build_audit()
    assert result["research_ttm_parent_attributable_net_income_cny"] == 44721506000
    assert result["eps_cny"] is None
    assert "weighted_average_ordinary_shares_not_verified" in result["per_share_blockers"]
    assert result["valuation_approved"] is False
    assert result["trade_approved"] is False
