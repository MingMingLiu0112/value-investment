import importlib.util
from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_p1_contract", ROOT / "scripts" / "freeze_moutai_p1_model_contract.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_p1_contract_keeps_primary_and_cross_check_separate():
    contract = MODULE.build()
    assert contract["specified_simulation_eligible"] is False
    assert contract["candidate_primary_model"]["conclusion"] == "not_admitted_for_specified_simulation"
    assert contract["necessary_cross_check"]["conclusion"] == "research_only_cross_check_not_formal_value"
    assert contract["discount_rate_evidence"]["company_operating_wacc"] is None


def test_parent_equity_contract_separates_model_from_historical_execution():
    spec = importlib.util.spec_from_file_location("parent_contract", ROOT / "scripts/freeze_moutai_p1_model_contract_v2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contract = module.build()
    assert contract["contract_version"] == "moutai-p1-model-contract-v3"
    assert "historical_execution" not in {gate["id"] for gate in contract["admission_gates"]}
    assert contract["candidate_primary_model"]["model_version"].endswith("-v2")
    assert contract["separate_execution_requirements"]["affects_valuation_admission"] is False
    assert contract["separate_execution_requirements"]["daily_simulation_policy_implemented"] is False
    assert contract["specified_simulation_eligible"] is False
    assert contract["trade_approved"] is False


def test_parent_contract_rejects_a_valid_hash_from_the_superseded_model(monkeypatch):
    spec = importlib.util.spec_from_file_location("parent_contract_mixed", ROOT / "scripts/freeze_moutai_p1_model_contract_v2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    inputs = dict(module.INPUTS)
    inputs["conditional_model"] = (
        "runtime/company-research/600519-consolidated-parent-equity-residual-income-20260914T095031Z/evidence.json",
        "d209392268f184111180a88740b19a643369774c5b1f6326f77e2815c18abae8")
    monkeypatch.setattr(module, "INPUTS", inputs)
    with pytest.raises(ValueError, match="dependency chain"):
        module.build()
