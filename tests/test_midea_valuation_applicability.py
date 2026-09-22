import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "midea_valuation_applicability", ROOT / "scripts" / "build_midea_valuation_applicability.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_midea_applicability_separates_economic_route_from_fact_scope():
    payload = MODULE.build_payload()
    pointer = ROOT / "runtime/company-research/midea-valuation-applicability-latest.json"
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    evidence = ROOT / pin["path"] / "evidence.json"
    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == pin["sha256"]

    assert payload["symbol"] == "000333"
    assert payload["package_version"] == "midea-valuation-applicability-v3"
    assert payload["profile_route"]["status"] == "SUPPORTED"
    assert payload["profile_route"]["model_type"] == "FCFF"
    assert payload["equity_route_profile_routing"]["status"] == "UNSUPPORTED"
    assert payload["scope_assessment"]["industrial_fcff_carve_out"] == "MODEL_NOT_APPLICABLE"
    assert payload["scope_assessment"]["consolidated_enterprise_value_bridge"] == "VALUATION_NOT_READY"
    assert payload["scope_assessment"]["fy2025_accounting_eps_denominator"] == "DISCLOSED_NOT_REGISTERED"
    assert payload["scope_assessment"]["announcement_date_share_scope"] == "DISCLOSED_NOT_REGISTERED"
    assert payload["scope_assessment"]["current_valuation_share_scope"] == "NOT_REGISTERED"
    assert payload["finance_company_size_observation"]["status"] == "OBSERVATION_NOT_MODEL_INPUT"
    assert payload["finance_company_size_observation"]["does_not_unblock_industrial_fcff"] is True
    assert payload["registered_valuation_model"] is None
    assert payload["registered_valuation_inputs"] == {}
    assert payload["alternative_route_candidate"]["model_id"] == "residual_income_or_equity_value"
    assert payload["alternative_route_candidate"]["status"] == "CANDIDATE_NOT_REGISTERED"
    assert payload["alternative_route_candidate"]["profile_authorization"] == "UNSUPPORTED"
    assert payload["alternative_route_candidate"]["evidence_status"]["historical_equity_income_and_cash_return_series"] == "COMPILED_CANDIDATE"
    assert payload["alternative_route_candidate"]["evidence_status"]["current_ordinary_share_denominator"] == "NOT_REGISTERED"
    assert payload["alternative_route_candidate"]["evidence_status"]["announcement_date_share_scope"] == "DISCLOSED_NOT_REGISTERED"
    assert any(item.startswith("Forward bear/base/bull ROE assumptions")
               for item in payload["alternative_route_candidate"]["required_next_evidence"])
    assert any(item.startswith("Clean-surplus equity rollforward")
               for item in payload["alternative_route_candidate"]["required_next_evidence"])
    assert not any("Historical" in item for item in payload["alternative_route_candidate"]["required_next_evidence"])
    assert "ordinary_shares" in payload["alternative_route_candidate"]["minimum_evidence_contract"]
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert {path["id"] for path in payload["paths"]} == {
        "industrial_fcff_carve_out", "consolidated_enterprise_value_bridge",
    }
    assert {ref["id"] for ref in payload["evidence_refs"]} == {
        "midea_ebit_scope", "midea_share_basis", "midea_consolidated_equity_scope",
        "midea_equity_return_history", "midea_finance_company_size_observation",
        "midea_hkex_20260330_share_basis",
    }
    assert all((ROOT / ref["path"]).is_relative_to(ROOT / "runtime/company-research")
               for ref in payload["evidence_refs"])


def test_midea_applicability_retains_no_arithmetic_model_or_trading_state():
    payload = MODULE.build_payload()

    assert payload["conclusion"].startswith("The economic profile supports the shared FCFF route")
    assert "bear" not in payload
    assert "base" not in payload
    assert "bull" not in payload
    assert "order" not in payload
    assert "position" not in payload
