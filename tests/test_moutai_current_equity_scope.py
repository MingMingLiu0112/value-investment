import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_scope", ROOT / "scripts/assess_moutai_current_equity_scope.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_current_scope_is_limited_to_same_date_paper_research():
    review = MODULE.build()
    assert review["decision"] == "admitted_for_bounded_same_date_paper_research_only"
    assert review["trade_approved"] is False
    assert any("must equal" in item.lower() for item in review["constraints"])
