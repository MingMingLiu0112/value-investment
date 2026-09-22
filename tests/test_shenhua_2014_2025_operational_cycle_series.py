import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_operating_cycle_series",
    ROOT / "scripts" / "build_shenhua_2014_2025_operational_cycle_series.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


@pytest.fixture(scope="module")
def payload():
    return MODULE.build_series()


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_series_is_source_bound_and_fail_closed(payload):
    assert payload["status"] == "multi_year_operational_cycle_series_collected_not_approved_as_model_inputs"
    assert payload["financial_scope_approved"] is False
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False

    rows = payload["series"]
    assert [row["year"] for row in rows] == list(range(2014, 2026))
    by_year = {row["year"]: row for row in rows}
    assert by_year[2014]["blended_average_coal_price_cny_per_tonne"] == 351.4
    assert by_year[2016]["self_produced_coal_sales_volume_million_tonnes"] == 285.5
    assert by_year[2019]["average_power_sale_price_cny_per_mwh"] is None
    assert by_year[2020]["average_power_sale_price_cny_per_mwh"] is None
    assert by_year[2022]["self_produced_coal_average_price_cny_per_tonne"] == 597.0
    assert by_year[2025]["self_produced_coal_sales_volume_million_tonnes"] == 332.3
    assert by_year[2025]["self_produced_coal_unit_production_cost_cny_per_tonne"] == 171.6
    assert by_year[2025]["average_power_sale_price_cny_per_mwh"] == 386.0

    assert not any("normalized_" in key for key in payload)
    assert "must not be paired with self-produced unit production cost" in payload["accounting_scope_warnings"][0]


def test_restatement_versions_are_preserved_without_mixing_them(payload):
    row_2024 = next(row for row in payload["series"] if row["year"] == 2024)
    restated = row_2024["restated_2025"]

    assert row_2024["coal_sales_volume_million_tonnes"] == 459.3
    assert restated["coal_sales_volume_million_tonnes"] == 460.2
    assert row_2024["blended_average_coal_price_cny_per_tonne"] == 564.0
    assert restated["blended_average_coal_price_cny_per_tonne"] == 563.0
    assert row_2024["self_produced_coal_sales_volume_million_tonnes"] == 327.0
    assert restated["self_produced_coal_sales_volume_million_tonnes"] == 337.6
    assert row_2024["self_produced_coal_unit_production_cost_cny_per_tonne"] == 179.0
    assert restated["self_produced_coal_unit_production_cost_cny_per_tonne"] == 180.2
    assert row_2024["electricity_sold_twh"] == 210.28
    assert restated["electricity_sold_twh"] == 215.41

    observations = {item["id"]: item for item in payload["restatement_observations"]}
    assert "2021_report_restated_2020_unit_cost" in observations
    assert "2025_report_restated_2024_and_2023_for_hangjin" in observations
    assert observations["2025_report_restated_2024_and_2023_for_hangjin"]["values"]["2024_unit_cost_original"] == 179.0
    assert observations["2025_report_restated_2024_and_2023_for_hangjin"]["values"]["2024_unit_cost_restated"] == 180.2


def test_every_value_has_a_hash_addressed_page(payload):
    source_hashes = {item["source_id"]: item["sha256"] for item in payload["sources"]}
    refs = payload["evidence_refs"]

    assert len(refs) >= 60
    assert all(ref["sha256"] == source_hashes[ref["source_id"]] for ref in refs)
    assert all(ref["page"] >= 1 for ref in refs)
    assert all(ref["metric"] for ref in refs)
    assert {ref["metric"] for ref in refs} == {
        "coal_volume_and_blended_price",
        "self_produced_coal_sales_volume",
        "self_produced_coal_average_price",
        "self_produced_coal_unit_production_cost",
        "electricity_sold",
        "average_power_sale_price",
        "restated_2024",
    }
    for row in payload["series"]:
        refs_for_year = [ref for ref in refs if ref["source_id"] in (row["source_id"], row["page_refs"]["self_produced_coal_sales_volume"]["source_id"])]
        assert refs_for_year


def test_pointer_and_manifest_match_generated_evidence(payload):
    pointer = json.loads(MODULE.POINTER.read_text(encoding="utf-8"))
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads((ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["script_sha256"] == _hash(Path(MODULE.__file__))
    assert set(manifest["source_sha256s"]) == {item["source_id"] for item in payload["sources"]}
    assert all(manifest["source_sha256s"][item["source_id"]] == item["sha256"] for item in payload["sources"])
