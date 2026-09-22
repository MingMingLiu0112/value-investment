import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_historical_capital_cost_policy",
    ROOT / "scripts" / "build_moutai_historical_capital_cost_policy.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def payload():
    return MODULE.build()


def test_package_is_fail_closed(payload):
    assert payload["symbol"] == "600519"
    assert payload["engineering_status"] == (
        "historical_capital_cost_policy_observation_package_complete"
    )
    assert payload["r1_status"] == "not_passed"
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["financial_scope_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["replay_eligible"] is False
    assert payload["strategy_backtest_complete"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert payload["registered_capital_cost_inputs"] == []


def test_source_pdf_is_hash_bound(payload):
    source = next(
        item for item in payload["evidence_refs"] if item["id"] == MODULE.SOURCE_ID
    )
    assert source["sha256"] == MODULE.SOURCE_SPEC["sha256"]
    assert _hash(ROOT / source["path"]) == source["sha256"]
    assert source["url"] == MODULE.SOURCE_SPEC["url"]


def test_appraisal_dates_and_observed_values_are_pinned(payload):
    observation = payload["appraisal_observation"]
    assert observation["report_number"] == "坤元评报〔2014〕364号"
    assert observation["report_date"] == "2014-10-14"
    assert observation["appraisal_base_date"] == "2014-07-31"
    assert observation["disclosure_url_path_date"] == "2014-10-24"
    assert observation["pdf_creation_metadata"] == "D:20141023173556Z"
    assert observation["observed_values"] == {
        "risk_free_rate_percent": "4.39",
        "equity_risk_premium_percent": "7.47",
        "subject_company_beta": "1.0766",
        "subject_company_specific_risk_percent": "2",
        "subject_company_cost_of_equity_percent": "14.43",
    }


def test_policy_raster_and_cost_of_equity_are_exact(payload):
    candidate = payload["capital_cost_policy_candidate"]
    assert candidate["status"] == "studied_stress_raster_unadmitted"
    assert candidate["risk_free_rate_percent"]["proposal"] == {
        "low": "3.4966",
        "base": "3.6251",
        "high": "3.75",
    }
    assert candidate["equity_risk_premium_percent"]["proposal"] == "7.47"
    assert candidate["beta"]["proposal"] == {
        "low": "0.80",
        "base": "1.00",
        "high": "1.20",
    }
    assert candidate["cost_of_equity_percent"]["proposal"] == {
        "low": "9.4726",
        "base": "11.0951",
        "high": "12.714",
    }
    assert candidate["cost_of_equity_percent"]["formula"] == "rf + beta * erp"
    for item in candidate.values():
        if isinstance(item, dict):
            assert item["admitted"] is False


def test_cement_specific_parameters_are_not_transferable(payload):
    blocked = payload["not_transferable_from_cement_subject"]
    assert blocked == {
        "subject_company_beta": "1.0766",
        "subject_company_specific_risk_percent": "2",
        "subject_company_cost_of_equity_percent": "14.43",
        "transfer_status": "not_transferable_to_moutai",
    }
    assert payload["appraisal_observation"]["transfer_boundary"]["beta"] == (
        "not_transferable_to_moutai"
    )
    assert payload["appraisal_observation"]["transfer_boundary"]["specific_risk"] == (
        "not_transferable_to_moutai"
    )
    assert payload["appraisal_observation"]["transfer_boundary"]["cost_of_equity"] == (
        "not_transferable_to_moutai"
    )


def test_unresolved_items_keep_parameter_registration_empty(payload):
    unresolved = payload["unresolved"]
    assert "exact_same_day_risk_free_term_structure" in unresolved
    assert "point_in_time_2015_moutai_beta" in unresolved
    assert "uniquely_correct_historical_equity_risk_premium" in unresolved
    assert "full_r1_point_in_time_decision_chain" in unresolved
    assert payload["registered_capital_cost_inputs"] == []
    assert any("A raster beta" in text for text in payload["not_proven"])
    assert any("professional appraisal ERP" in text for text in payload["definition_breaks"])
    assert any("Transfer the cement subject" in text for text in payload["forbidden_calculations"])


def test_all_evidence_references_are_hash_bound(payload):
    expected = {MODULE.SOURCE_ID} | {item["id"] for item in MODULE.PRIOR_EVIDENCE}
    refs = {item["id"]: item for item in payload["evidence_refs"]}
    assert set(refs) == expected
    for item in refs.values():
        target = ROOT / item["path"]
        assert target.exists()
        assert _hash(target) == item["sha256"]


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (
            ROOT
            / "runtime/company-research/moutai-historical-capital-cost-policy-latest.json"
        ).read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads((ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["script_sha256"] == _hash(Path(MODULE.__file__))
    assert manifest["source_sha256s"] == {MODULE.SOURCE_ID: MODULE.SOURCE_SPEC["sha256"]}
    assert manifest["prior_evidence_sha256s"] == {
        item["id"]: item["sha256"] for item in MODULE.PRIOR_EVIDENCE
    }
