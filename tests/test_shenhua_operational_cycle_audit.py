import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_operating_cycle_audit",
    ROOT / "scripts" / "build_shenhua_operational_cycle_audit.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def payload():
    return MODULE.build()


def test_operational_cycle_audit_is_fail_closed(payload):
    assert payload["engineering_status"] == "operational_cycle_audit_complete"
    assert payload["status"] == "operational_cycle_series_audited_as_period_evidence_only"
    assert payload["financial_scope_approved"] is False
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert payload["registered_cyclical_facts_operating_inputs"] == []


def test_fields_are_period_facts_not_model_inputs(payload):
    decisions = payload["field_decisions"]

    assert decisions["coal_sales_volume_million_tonnes"]["coverage"] == "12/12"
    assert decisions["self_produced_coal_average_price_cny_per_tonne"]["coverage"] == "4/12"
    assert decisions["average_power_sale_price_cny_per_mwh"]["excluded_years"] == [2019, 2020]
    assert decisions["blended_average_coal_price_cny_per_tonne"]["model_input"] is None
    assert decisions["self_produced_coal_unit_production_cost_cny_per_tonne"]["model_input"] is None

    assert payload["model_input_decisions"]["unit_cost"] == "rejected_as_direct_model_input_historical_production_cost_only"
    assert payload["model_input_decisions"]["ordinary_shares"] == "separate_point_in_time_denominator_approved_but_not_registered"


def test_point_in_time_and_scope_boundaries_are_explicit(payload):
    volume = payload["field_decisions"]["self_produced_coal_sales_volume_million_tonnes"]
    assert volume["later_year_comparative_years"] == [2014, 2015, 2017, 2019]

    findings = {item["id"]: item for item in payload["specific_findings"]}
    assert "production_is_not_sales_2025" in findings
    assert "332.1" in findings["production_is_not_sales_2025"]["fact"]
    assert "332.3" in findings["production_is_not_sales_2025"]["fact"]
    assert findings["later_year_comparative_volume_provenance"]["years"] == [2014, 2015, 2017, 2019]
    assert "must not be subtracted" in findings["blended_price_unit_cost_pairing_forbidden"]["fact"]

    assert any("must not use that later filing's comparative value" in text for text in payload["point_in_time_policy"])
    assert any("blended_average_coal_price - self_produced_unit_production_cost" in text for text in payload["forbidden_calculations"])


def test_reviewed_evidence_references_are_hash_bound(payload):
    for item in payload["evidence_refs"]:
        target = ROOT / item["path"]
        assert target.exists()
        assert _hash(target) == item["sha256"]


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads((ROOT / "runtime/company-research/shenhua-2014-2025-operational-cycle-audit-latest.json").read_text(encoding="utf-8"))
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads((ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["script_sha256"] == _hash(Path(MODULE.__file__))
    assert manifest["operating_series_sha256"] == json.loads(
        (ROOT / "runtime/company-research/shenhua-2014-2025-operational-cycle-series-latest.json").read_text(encoding="utf-8")
    )["sha256"]

    series_pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-2014-2025-operational-cycle-series-latest.json").read_text(encoding="utf-8")
    )
    series = json.loads((ROOT / series_pointer["path"] / "evidence.json").read_text(encoding="utf-8"))
    sources = {item["source_id"]: item for item in series["sources"]}

    for source_id, source_hash in manifest["source_sha256s"].items():
        assert source_id.startswith("shenhua_")
        assert sources[source_id]["sha256"] == source_hash
        assert _hash(ROOT / sources[source_id]["path"]) == source_hash
