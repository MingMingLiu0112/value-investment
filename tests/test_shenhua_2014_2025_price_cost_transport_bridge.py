import hashlib
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_price_cost_transport_bridge",
    ROOT / "scripts" / "build_shenhua_2014_2025_price_cost_transport_bridge.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def payload():
    return MODULE.build()


def test_price_cost_transport_bridge_is_source_bound_and_fail_closed(payload):
    assert payload["engineering_status"] == "price_cost_transport_bridge_complete"
    assert payload["status"] == "point_in_time_external_price_and_cost_transport_bridge_compiled_not_reviewed_or_approved"
    assert payload["financial_scope_approved"] is False
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert payload["registered_cyclical_facts_operating_inputs"] == []
    assert [row["year"] for row in payload["external_price_envelope"]] == list(range(2014, 2026))
    assert all(row["model_input"] is None for row in payload["external_price_envelope"])


def test_external_price_envelope_pins_values_and_disclosure_gaps(payload):
    rows = {row["year"]: row for row in payload["external_price_envelope"]}

    assert rows[2014]["period_end_price_cny_per_tonne"] == 525
    assert rows[2014]["annual_average_price_cny_per_tonne"] == 522
    assert rows[2014]["low_cny_per_tonne"] == 478
    assert rows[2015]["annual_average_price_cny_per_tonne"] == 427
    assert rows[2016]["period_end_price_cny_per_tonne"] == 593
    assert rows[2017]["annual_average_price_cny_per_tonne"] == 585.3
    assert rows[2020]["period_end_price_cny_per_tonne"] == 585
    assert rows[2021]["annual_average_price_cny_per_tonne"] == 673
    assert rows[2022]["annual_average_price_cny_per_tonne"] == 737

    assert rows[2018]["page"] is None
    assert rows[2018]["period_end_price_cny_per_tonne"] is None
    assert rows[2018]["annual_average_price_cny_per_tonne"] is None
    assert rows[2019]["availability"] == "range_or_gap"
    assert rows[2019]["range_low_cny_per_tonne"] == 550
    assert rows[2019]["range_high_cny_per_tonne"] == 650

    assert rows[2023]["benchmark"] == "ncei_5500_kcal_long_term"
    assert rows[2023]["annual_average_price_cny_per_tonne"] == 714
    assert rows[2023]["qhd_5500_spot_annual_average_cny_per_tonne"] == 980
    assert rows[2024]["annual_average_price_cny_per_tonne"] == 701
    assert rows[2024]["qhd_5500_spot_annual_average_cny_per_tonne"] == 861
    assert rows[2025]["annual_average_price_cny_per_tonne"] == 680
    assert rows[2025]["qhd_5500_spot_annual_average_cny_per_tonne"] == 703


def test_2025_internal_bridge_keeps_company_prices_apart_from_market_prices(payload):
    bridge = payload["internal_cost_transport_bridge_2025"]
    coal = bridge["coal"]
    power = bridge["power"]
    transport = bridge["transport"]

    assert coal["self_produced_average_price_cny_per_tonne"] == 472
    assert coal["blended_average_price_cny_per_tonne"] == 495
    assert coal["annual_long_term_price_cny_per_tonne"] == 455
    assert coal["internal_power_sales_volume_million_tonnes"] == 73.2
    assert coal["internal_power_sales_price_cny_per_tonne"] == 447
    assert coal["self_produced_gross_profit_cny_millions"] == 62_820
    assert coal["unit_production_cost_cny_per_tonne"] == 171.6
    assert coal["unit_production_cost_components"]["depreciation_amortisation"] == 22.2

    assert power["electricity_sold_twh"] == 207.00
    assert power["average_power_sale_price_cny_per_mwh"] == 386
    assert power["unit_sale_cost_cny_per_mwh"] == 334.7
    assert power["internal_coal_consumed_million_tonnes"] == 77.7
    assert power["total_coal_consumed_million_tonnes"] == 97.7
    assert power["coal_power_fuel_and_energy_cost_cny_millions"] == 47_702

    assert transport["railway_unit_cost_cny_per_tonne_km"] == 0.082
    assert transport["port_unit_cost_cny_per_tonne"] == 11.5
    assert transport["shipping_unit_cost_cny_per_tonne_nautical_mile"] == 0.030


def test_derived_ratios_are_kept_as_unreconciled_candidates(payload):
    ratios = payload["derived_candidates_not_reconciled"]
    assert Decimal(ratios["self_produced_revenue_per_tonne_cny"]) == Decimal("472.184772796")
    assert Decimal(ratios["self_produced_sales_cost_per_tonne_cny"]) == Decimal("283.138730063")
    assert Decimal(ratios["coal_segment_cost_per_group_tonne_cny"]) == Decimal("358.855883036")
    assert Decimal(ratios["power_fuel_cost_per_internal_coal_tonne_cny"]) == Decimal("613.925353925")
    assert ratios["ncei_average_minus_company_annual_contract_price_cny"] == "225"
    assert ratios["qhd_spot_average_minus_blended_realized_price_cny"] == "208"


def test_boundaries_and_forbidden_calculations_are_explicit(payload):
    findings = {item["id"]: item for item in payload["specific_findings"]}
    assert "external_benchmark_definition_changes_in_2023" in findings
    assert "2018_external_benchmark_gap" in findings
    assert "2019_is_range_not_point" in findings
    assert "internal_power_coal_bridge_is_unreconciled" in findings
    assert "segments_do_not_add_to_group_profit_without_reconciliation" in findings
    assert "73.2 Mt" in findings["internal_power_coal_bridge_is_unreconciled"]["fact"]
    assert "77.7 Mt" in findings["internal_power_coal_bridge_is_unreconciled"]["fact"]

    assert any("secondary provenance" in text for text in payload["point_in_time_policy"])
    assert any("external benchmark price - disclosed unit production cost" in text for text in payload["forbidden_calculations"])
    assert all(
        decision.startswith("not_derived")
        for name, decision in payload["model_input_decisions"].items()
        if name != "unit_cost"
    )


def test_reviewed_evidence_references_are_hash_bound(payload):
    for item in payload["evidence_refs"]:
        target = ROOT / item["path"]
        assert target.exists()
        assert _hash(target) == item["sha256"]


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-2014-2025-price-cost-transport-bridge-latest.json").read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads((ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["script_sha256"] == _hash(Path(MODULE.__file__))
    assert set(manifest["source_sha256s"]) == {
        f"shenhua_{year}_annual_report" for year in range(2014, 2026)
    }
    assert manifest["prior_evidence_sha256s"]["attributable_profit_series"] == json.loads(
        (ROOT / "runtime/company-research/shenhua-2014-2025-attributable-profit-series-latest.json").read_text(encoding="utf-8")
    )["sha256"]

    payload = json.loads(target.read_text(encoding="utf-8"))
    sources = {item["id"]: item for item in payload["evidence_refs"] if item["id"].startswith("shenhua_20")}
    for source_id, source_hash in manifest["source_sha256s"].items():
        assert sources[source_id]["sha256"] == source_hash
        assert _hash(ROOT / sources[source_id]["path"]) == source_hash
