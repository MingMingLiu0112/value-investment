import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_candidate_inputs",
    ROOT / "scripts" / "build_shenhua_cyclical_candidate_inputs.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_candidate_package_is_source_bound_and_fail_closed():
    payload = MODULE.build()
    source = ROOT / "runtime/shenhua-2025-official.pdf"

    assert payload["status"] == "cyclical_candidate_inputs_compiled_not_reviewed_or_approved"
    assert payload["financial_scope_approved"] is False
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False

    refs = [ref for derivation in payload["candidate_derivations"].values()
            for ref in derivation["evidence_refs"]]
    assert refs
    assert all(ref["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest() for ref in refs)
    assert all(ref["page"] > 0 for ref in refs)


def test_candidate_derivations_are_recorded_without_becoming_model_inputs():
    payload = MODULE.build()
    derivations = payload["candidate_derivations"]

    assert derivations["cash_tax_rate"]["candidate_values"]["2025"].startswith("0.2081")
    assert derivations["cash_tax_rate"]["candidate_values"]["2024_restated"].startswith("0.2111")
    assert derivations["normalized_working_capital_change"]["candidate_values"]["raw_change_cny"] == "6501000000"
    assert derivations["resource_life_years"]["candidate_values"]["jorc_over_current_output_years"].startswith("33.5")
    assert derivations["resource_life_years"]["candidate_values"]["china_recoverable_over_current_output_years"].startswith("52.1")
    assert derivations["ordinary_shares"]["model_input"] is None
    assert derivations["normalized_parent_operating_profit"]["candidate_values"] == {}
    assert derivations["normalized_parent_operating_profit"]["status"] == "cannot_derive_from_retained_disclosure"
    assert all(derivation["model_input"] is None for derivation in derivations.values())


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-cyclical-candidate-inputs-latest.json").read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads(
        (ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8")
    )

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["source_sha256"] == MODULE.SOURCE_HASH


def test_candidate_package_links_existing_scope_and_series_evidence():
    payload = MODULE.build()
    linked = {item["id"]: item for item in payload["linked_evidence"]}
    assert set(linked) == {"shenhua_cyclical_scope", "shenhua_cyclical_time_series"}
    for item in linked.values():
        source = ROOT / item["path"]
        assert source.exists()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == item["sha256"]
    assert linked["shenhua_cyclical_scope"]["status"] == "cyclical_scope_blocked_no_verified_mid_cycle_time_series"
    assert linked["shenhua_cyclical_time_series"]["status"] == "multi_year_raw_series_collected_but_not_approved_as_normalized_inputs"
