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
    assert payload["package_version"] == "midea-valuation-applicability-v4"
    assert payload["blocker_classification"]["A_BLOCKING_UNKNOWN"] == 1
    assert payload["blocker_classification"]["B_SCENARIO_RANGE_INPUT"] == 6
    assert len(payload["blockers"]) == payload["blocker_classification"]["A_BLOCKING_UNKNOWN"]
    assert len(payload["evidence_stops"]) == payload["blocker_classification"]["D_EVIDENCE_STOP"]
    assert payload["profile_route"]["status"] == "SUPPORTED"
    assert payload["profile_route"]["model_type"] == "FCFF"
    assert payload["equity_route_profile_routing"]["status"] == "SUPPORTED"
    assert payload["scope_assessment"]["valuation_basis_2026_06_30_share_scope"] == "A_BLOCKING_UNKNOWN"
    assert payload["scope_assessment"]["post_period_2026_09_29_share_scope"] == "VERIFIED_NOT_BACKDATED"
    assert payload["scope_assessment"]["industrial_fcff_carve_out"] == "MODEL_NOT_APPLICABLE"
    assert payload["scope_assessment"]["consolidated_enterprise_value_bridge"] == "VALUATION_NOT_READY"
    assert payload["scope_assessment"]["fy2025_accounting_eps_denominator"] == "DISCLOSED_NOT_REGISTERED"
    assert payload["scope_assessment"]["announcement_date_share_scope"] == "DISCLOSED_NOT_REGISTERED"
    assert payload["finance_company_size_observation"]["status"] == "OBSERVATION_NOT_MODEL_INPUT"
    assert payload["finance_company_size_observation"]["does_not_unblock_industrial_fcff"] is True
    assert payload["registered_valuation_model"] is None
    assert payload["registered_valuation_inputs"] == {}
    assert payload["alternative_route_candidate"]["model_id"] == "residual_income_or_equity_value"
    assert payload["alternative_route_candidate"]["status"] == "PROFILE_AUTHORIZED_INPUTS_INCOMPLETE"
    assert payload["alternative_route_candidate"]["profile_authorization"] == "SUPPORTED"
    assert payload["alternative_route_candidate"]["evidence_status"]["historical_equity_income_and_cash_return_series"] == "COMPILED_CANDIDATE_NOT_REGISTERED"
    assert payload["alternative_route_candidate"]["evidence_status"]["post_period_ordinary_share_denominator"] == "VERIFIED_2026_09_29_NOT_BACKDATED"
    assert payload["alternative_route_candidate"]["evidence_status"]["valuation_basis_ordinary_share_denominator"] == "A_BLOCKING_UNKNOWN_2026_06_30_NOT_BOUNDED"
    assert payload["alternative_route_candidate"]["evidence_status"]["announcement_date_share_scope"] == "DISCLOSED_NOT_REGISTERED"
    assert any(item.startswith("Exact 2026-06-30 ordinary-share denominator")
               for item in payload["alternative_route_candidate"]["required_next_evidence"])
    assert any(item.startswith("Bear/base/bull ROE paths")
               for item in payload["alternative_route_candidate"]["scenario_inputs_to_register"])
    assert not any("Historical" in item for item in payload["alternative_route_candidate"]["required_next_evidence"])
    assert "ordinary_shares" in payload["alternative_route_candidate"]["minimum_evidence_contract"]
    assert payload["formal_fair_value"] is None
    assert payload["registered_valuation_model"] is None
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["model_change"]["baseline_v13_rewritten"] is False
    assert payload["model_change"]["valuation_run_status"] == "NOT_RUN_A_BLOCKING_SHARE_DENOMINATOR"
    assert payload["valuation_approved"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert {path["id"] for path in payload["paths"]} == {
        "industrial_fcff_carve_out", "consolidated_enterprise_value_bridge",
        "shared_residual_income_equity",
    }
    assert {ref["id"] for ref in payload["evidence_refs"]} == {
        "midea_ebit_scope", "midea_share_basis", "midea_consolidated_equity_scope",
        "midea_equity_return_history", "midea_finance_company_size_observation",
        "midea_hkex_20260330_share_basis", "midea_2026h1_equity_change_report",
        "midea_2026_09_29_hkex_share_report",
    }
    assert all((ROOT / ref["path"]).is_relative_to(ROOT / "runtime")
               for ref in payload["evidence_refs"])


def test_midea_applicability_retains_no_arithmetic_model_or_trading_state():
    payload = MODULE.build_payload()

    assert payload["conclusion"].startswith("FCFF is not applicable")
    assert payload["registered_valuation_inputs"] == {}
    assert payload["formal_fair_value"] is None
    assert payload["alternative_route_candidate"]["decision"] == (
        "AUTHORIZED_NOT_RUN_A_BLOCKING_SHARE_DENOMINATOR"
    )
    assert "order" not in payload
    assert "position" not in payload
