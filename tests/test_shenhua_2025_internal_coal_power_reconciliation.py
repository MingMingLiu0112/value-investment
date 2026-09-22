import hashlib
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_internal_coal_power_reconciliation",
    ROOT / "scripts" / "build_shenhua_2025_internal_coal_power_reconciliation.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


@pytest.fixture(scope="module")
def payload():
    return MODULE.build()


def test_internal_coal_power_package_is_fail_closed(payload):
    assert payload["engineering_status"] == "internal_coal_power_reconciliation_evidence_boundary_complete"
    assert payload["status"] == "sales_and_consumption_basis_documented_no_explicit_volume_bridge_found"
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert payload["registered_cyclical_facts_operating_inputs"] == []


def test_sales_and_consumption_measures_are_pinned_without_forced_equality(payload):
    sales = payload["coal_segment_internal_sales_2025"]
    consumption = payload["power_segment_consumption_2025"]
    reconciliation = payload["volume_reconciliation"]

    assert sales["basis"] == "coal sales volume"
    assert sales["internal_power_sales_million_tonnes"] == 73.2
    assert sales["internal_power_sales_price_cny_per_tonne"] == 447
    assert sales["total_sales_million_tonnes"] == 430.9

    assert consumption["basis"] == "coal consumed by power segment"
    assert consumption["internal_group_coal_consumed_million_tonnes"] == 77.7
    assert consumption["total_coal_consumed_million_tonnes"] == 97.7
    assert consumption["internal_share_pct"] == 79.5
    assert consumption["coal_power_raw_material_fuel_power_cost_cny_millions"] == 47_702

    assert Decimal(reconciliation["difference_million_tonnes"]) == Decimal("4.5")
    assert Decimal(reconciliation["derived_external_power_coal_million_tonnes"]) == Decimal("20.0")
    assert reconciliation["explicit_reconciliation_disclosed"] is False
    assert reconciliation["reconciliation_status"] == "not_reconciled_by_disclosed_data"


def test_inventory_and_fuel_cost_cannot_manufacture_a_bridge(payload):
    inventory = payload["inventory_boundary"]
    fuel = payload["fuel_cost_boundary"]

    assert inventory["group_coal_inventory_end_million_tonnes"] == 23.4
    assert inventory["inventory_versus_beginning_pct"] == -2.5
    assert inventory["power_plant_fuel_inventory_volume_bridge_disclosed"] is False

    assert fuel["raw_material_fuel_power_cost_cny_millions"] == 47_702
    assert Decimal(fuel["simple_division_by_77_7_mt_cny_per_tonne"]) == Decimal("613.925353925")
    assert fuel["is_internal_transfer_price"] is False


def test_candidate_explanations_are_not_upgraded_to_facts(payload):
    explanations = {item["id"]: item for item in payload["candidate_explanations"]}

    assert explanations["sales_volume_versus_consumption_volume"]["status"] == "definitional_basis_difference"
    assert explanations["sales_volume_versus_consumption_volume"]["supported_by_disclosure"] is True
    assert explanations["power_plant_inventory_movement"]["supported_by_disclosure"] is False
    assert explanations["direct_external_power_purchases_counted_as_internal"]["status"] == "contradicted_by_disclosure_label"
    assert explanations["heat_quality_and_moisture_measurement_difference"]["supported_by_disclosure"] is False


def test_targeted_search_does_not_claim_a_hidden_bridge_was_found(payload):
    search = payload["search_scope"]
    assert search["method"].startswith("targeted text search")
    assert search["no_page_contains_both_73_2_and_77_7"]["chinese"] is True
    assert search["no_page_contains_both_73_2_and_77_7"]["english"] is True
    assert "not proof" in search["absence_note"]


def test_model_inputs_remain_null_and_forbidden_math_is_explicit(payload):
    decisions = payload["model_input_decisions"]
    assert all(item["model_input"] is None for item in decisions.values())
    assert "447 CNY/t is an internal accounting transfer price" in decisions["normalized_mid_cycle_coal_price"]["reason"]
    assert "47,702 million CNY" in decisions["normalized_power_fuel_unit_cost"]["reason"]
    assert any("73.2 Mt * 447 CNY/t" in item for item in payload["forbidden_calculations"])
    assert any("47,702 million CNY / 77.7 Mt" in item for item in payload["forbidden_calculations"])


def test_evidence_refs_are_hash_bound_and_exist(payload):
    expected_source_hashes = {
        "shenhua_2025_chinese_annual_report": MODULE.SOURCE_CN_HASH,
        "shenhua_2025_english_annual_report": MODULE.SOURCE_EN_HASH,
    }
    source_ids = {
        "shenhua_cn_coal_source_page_30",
        "shenhua_cn_internal_external_customer_page_31",
        "shenhua_cn_power_consumption_page_38",
        "shenhua_cn_inventory_page_24",
        "shenhua_cn_coal_chemical_page_41",
        "shenhua_cn_segment_policy_page_459",
        "shenhua_en_internal_external_customer_page_46",
        "shenhua_en_power_consumption_page_57",
        "shenhua_en_inventory_page_34",
        "shenhua_en_segment_policy_page_287",
        "shenhua_price_cost_transport_bridge",
    }
    refs = {item["id"]: item for item in payload["evidence_refs"]}
    assert source_ids.issubset(refs)
    for item in refs.values():
        target = ROOT / item["path"]
        assert target.exists()
        assert _hash(target).lower() == item["sha256"].lower()

    manifest = json.loads((ROOT / "runtime/company-research/shenhua-2025-internal-coal-power-reconciliation-20260922/manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_sha256s"] == expected_source_hashes


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-2025-internal-coal-power-reconciliation-latest.json").read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads((ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["script_sha256"] == _hash(Path(MODULE.__file__))
    prior = json.loads((ROOT / "runtime/company-research/shenhua-2014-2025-price-cost-transport-bridge-latest.json").read_text(encoding="utf-8"))
    assert manifest["prior_evidence_sha256s"]["price_cost_transport_bridge"] == prior["sha256"]
