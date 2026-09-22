import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_current_valuation_admission", ROOT / "scripts" / "audit_moutai_current_valuation_admission.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_current_conditional_valuation_is_not_admitted_as_fair_value_or_trade():
    result = MODULE.audit()
    assert result["formal_fair_value"] is None
    assert result["valuation_approved"] is False
    assert result["trade_approved"] is False
    assert result["p1_current_model_admitted"] is True
    assert {gate["id"] for gate in result["gates"] if not gate["passed"]} == set(result["blocking_gate_ids"])
    assert result["blocking_gate_ids"] == []
    assert "historical_execution" not in result["blocking_gate_ids"]
    assert result["admission_version"] == "current-valuation-admission-v3"
    assert result["separate_execution_requirements"]["affects_valuation_admission"] is False
    assert result["separate_execution_requirements"]["daily_simulation_policy_implemented"] is True
    assert "market_session" not in result["blocking_gate_ids"]
    assert "paper_execution" not in result["blocking_gate_ids"]
    assert result["current_capital_bridge_evidence"]["path"].endswith("evidence.json")
    assert result["current_cost_policy_evidence"]["path"].endswith("evidence.json")
    assert result["current_forward_assumptions_evidence"]["path"].endswith("evidence.json")
    assessment = result["model_scope_assessment"]
    assert assessment["primary_model"]["name"] == "consolidated_parent_equity_residual_income_or_dividend_capacity"
    assert assessment["cross_check"]["name"] == "cash_distribution_anchored_equity_range"
    assert assessment["conclusion"] == "admitted_for_bounded_current_paper_research"
    assert "paper-account decision input" in assessment["allowed_output"]
