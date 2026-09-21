from decimal import Decimal
import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_parent_equity_discount_range", ROOT / "scripts" / "build_moutai_consolidated_equity_discount_range.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_scope_matched_discount_range_is_ordered_and_unapproved():
    result = MODULE.build()
    values = [Decimal(result["range"][key]) for key in ("lower", "central", "upper")]
    assert values[0] < values[1] < values[2]
    assert result["selection_status"] == "bounded_research_range_not_single_selected_rate"
    assert result["valuation_approved"] is False
    assert result["simulation_eligible"] is False
    assert result["trade_approved"] is False
