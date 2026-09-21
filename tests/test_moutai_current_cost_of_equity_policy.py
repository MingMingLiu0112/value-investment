import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_current_cost_policy", ROOT / "scripts" / "assess_moutai_current_cost_of_equity_policy.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_current_cost_policy_is_dated_range_selection_not_trade_approval():
    result = MODULE.build()
    assert result["passed"] is True
    model, _ = MODULE.pinned_json(__import__("json").loads(MODULE.MODEL_POINTER.read_text(encoding="utf-8")))
    assert result["as_of"] == model["valuation_at"][:10]
    assert result["selection"]["scenario_mapping"] == {
        "bear": "upper", "base": "central", "bull": "lower",
    }
    assert result["selection"]["additional_base_stress"] == "+200bp"
    assert float(result["selection"]["model_serialization_max_difference"]) < 1e-24
    assert result["valuation_approved"] is False
    assert result["trade_approved"] is False
