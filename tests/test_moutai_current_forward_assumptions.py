import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_current_forward_assumptions", ROOT / "scripts" / "assess_moutai_current_forward_assumptions.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_forward_assumption_review_is_bounded_and_keeps_counterevidence():
    result = MODULE.build()
    assert result["passed"] is True
    assert result["earnings_policy"]["scenarios"] == {"bear": "-0.05", "base": "0", "bull": "0.05"}
    assert result["capital_and_fade_policy"]["payout_stresses"] == ["0.50", "0.85"]
    assert len(result["counterevidence"]) == 4
    assert result["valuation_approved"] is False
    assert result["trade_approved"] is False
