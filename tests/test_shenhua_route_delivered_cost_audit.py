import hashlib
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_route_delivered_cost_audit",
    ROOT / "scripts" / "build_shenhua_route_delivered_cost_audit.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def payload():
    return MODULE.build()


def test_route_delivered_cost_audit_is_fail_closed(payload):
    assert payload["engineering_status"] == "route_specific_delivered_cost_disclosure_audit_complete"
    assert payload["status"] == "route_specific_delivered_cost_not_disclosed_or_approved"
    assert payload["financial_scope_approved"] is False
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert payload["registered_cyclical_facts_operating_inputs"] == []


def test_audit_searches_all_retained_chinese_reports_and_2025_english_report(payload):
    scope = payload["search_scope"]
    searched = payload["search_results_by_source"]

    assert scope["years"] == list(range(2014, 2026))
    assert scope["source_count"] == 13
    assert scope["pages_scanned"] > 3_000
    assert {(item["year"], item["language"]) for item in searched} >= {
        (year, "zh") for year in range(2014, 2026)
    } | {(2025, "en")}


def test_route_names_are_found_but_no_route_specific_metric_phrases_exist(payload):
    cn_2025 = next(
        item for item in payload["search_results_by_source"]
        if item["source_id"] == "shenhua_2025_annual_report"
    )

    assert cn_2025["route_name_pages"]["朔黄"]
    assert cn_2025["route_name_pages"]["神朔"]
    assert payload["route_specific_metric_phrase_hits"] == {}
    assert payload["explicit_allocation_term_hits"] == {}
    assert "route_names_in_narrative_are_not_throughput_disclosures" in {
        item["id"] for item in payload["specific_findings"]
    }


def test_aggregate_facts_are_source_bound_and_kept_separate_from_route_cost(payload):
    facts = payload["aggregate_transport_facts_2025"]

    assert facts["coal"]["self_produced_unit_production_cost_cny_per_tonne"] == 171.6
    assert facts["railway"]["turnover_billion_tonne_km"] == 313.0
    assert facts["railway"]["disclosed_unit_cost_cny_per_tonne_km"] == 0.082
    assert facts["ports"]["huanghua_loading_million_tonnes"] == 217.0
    assert facts["ports"]["tianjin_coal_terminal_loading_million_tonnes"] == 44.6
    assert facts["ports"]["disclosed_unit_cost_cny_per_tonne"] == 11.5
    assert facts["shipping"]["freight_volume_million_tonnes"] == 111.3
    assert facts["shipping"]["turnover_billion_tonne_nautical_miles"] == 114.9
    assert facts["shipping"]["disclosed_unit_cost_cny_per_tonne_nautical_mile"] == 0.030


def test_simple_segment_divisions_are_marked_forbidden_not_approved(payload):
    proxies = payload["derived_proxies_forbidden_not_approved"]

    assert Decimal(proxies["railway_segment_cost_per_group_coal_sale_tonne_cny"]) == Decimal("63.026224181945")
    assert Decimal(proxies["port_segment_cost_per_reported_huanghua_tianjin_loading_tonne_cny"]) == Decimal("14.311926605505")
    assert Decimal(proxies["shipping_segment_cost_per_shipping_freight_tonne_cny"]) == Decimal("31.734052111411")
    assert "double counts internal transfers" in proxies["why_forbidden"]

    assert any("171.6 + railway segment cost" in item for item in payload["forbidden_calculations"])
    assert any("railway segment cost / 430.9 Mt" in item for item in payload["forbidden_calculations"])
    assert any("shipping segment cost / 111.3 Mt" in item for item in payload["forbidden_calculations"])


def test_missing_route_facts_and_model_decisions_remain_null(payload):
    assert "route_specific_railway_tonne_km" in payload["missing_route_facts"]
    assert "mine_to_port_volume_allocation" in payload["missing_route_facts"]
    assert "all_in_delivered_cost_by_route" in payload["missing_route_facts"]
    assert all(item["model_input"] is None for item in payload["model_input_decisions"].values())
    assert payload["model_input_decisions"]["unit_cost"]["status"].startswith("not_derived")


def test_evidence_refs_are_hash_bound_and_exist(payload):
    source_ids = {
        f"shenhua_{year}_annual_report" for year in range(2014, 2026)
    } | {"shenhua_2025_english_annual_report"}
    source_refs = [
        item for item in payload["evidence_refs"]
        if item["id"] in source_ids
    ]
    assert len(source_refs) == 13
    for item in source_refs:
        target = ROOT / item["path"]
        assert target.exists()
        assert _hash(target) == item["sha256"].lower()


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(MODULE.POINTER.read_text(encoding="utf-8"))
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads((ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["script_sha256"] == _hash(Path(MODULE.__file__))
    assert len(manifest["source_sha256s"]) == 13
    assert manifest["prior_evidence_sha256s"]["price_cost_transport_bridge"] == json.loads(
        MODULE.PRIOR_POINTER.read_text(encoding="utf-8")
    )["sha256"]

    payload = json.loads(target.read_text(encoding="utf-8"))
    source_ids = {
        f"shenhua_{year}_annual_report" for year in range(2014, 2026)
    } | {"shenhua_2025_english_annual_report"}
    source_by_id = {
        item["id"]: item
        for item in payload["evidence_refs"]
        if item["id"] in source_ids
    }
    for source_id, source_hash in manifest["source_sha256s"].items():
        assert source_by_id[source_id]["sha256"].lower() == source_hash.lower()
        assert _hash(ROOT / source_by_id[source_id]["path"]) == source_hash.lower()
