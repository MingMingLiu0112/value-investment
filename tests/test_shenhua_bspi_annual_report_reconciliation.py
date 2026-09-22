import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_bspi_annual_report_reconciliation",
    ROOT / "scripts" / "build_shenhua_bspi_annual_report_reconciliation.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def payload():
    return MODULE.build()


def test_reconciliation_package_is_fail_closed(payload):
    assert payload["symbol"] == "601088"
    assert payload["engineering_status"] == "bspi_annual_report_reconciliation_package_complete"
    assert payload["status"].startswith("seven_bspi_annual_means_match")
    assert payload["financial_scope_approved"] is False
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert payload["registered_cyclical_facts_operating_inputs"] == []
    assert all(row["model_input"] is None for row in payload["comparisons"])


def test_seven_reported_annual_averages_match_within_half_unit(payload):
    rows = {row["year"]: row for row in payload["comparisons"]}
    expected = {
        2014: ("522.46", "0.46", "-2.00"),
        2015: ("427.10", "0.10", "0.00"),
        2016: ("459.58", "-0.42", "0.00"),
        2017: ("585.16", "-0.14", "-1.00"),
        2020: ("549.41", "0.41", "0.00"),
        2021: ("672.90", "-0.10", "0.00"),
        2022: ("736.51", "-0.49", "0.00"),
    }
    assert payload["summary"]["comparable_reported_average_years"] == 7
    assert payload["summary"]["all_mean_differences_within_half_unit"] is True
    assert payload["summary"]["maximum_absolute_mean_difference_cny_per_tonne"] == "0.49"
    assert payload["summary"]["exact_year_end_match_years"] == [2015, 2016, 2020, 2021, 2022]
    assert payload["summary"]["year_end_off_by_date_alignment_years"] == [2014, 2017]
    for year, expected_values in expected.items():
        row = rows[year]
        assert row["endpoint_simple_mean_cny_per_tonne"] == expected_values[0]
        assert row["mean_difference_cny_per_tonne"] == expected_values[1]
        assert row["period_end_difference_cny_per_tonne"] == expected_values[2]


def test_noncomparable_years_are_not_promoted_to_model_inputs(payload):
    rows = {row["year"]: row for row in payload["comparisons"]}
    assert rows[2018]["report_status"] == "no_comparable_annual_average"
    assert rows[2019]["report_status"] == "issuer_reported_range_only"
    for year in (2023, 2024, 2025):
        assert rows[year]["report_status"] == "issuer_benchmark_switched_to_ncei"
        assert rows[year]["mean_difference_cny_per_tonne"] is None
        assert rows[year]["period_end_difference_cny_per_tonne"] is None


def test_caveats_are_recorded(payload):
    findings = {item["id"]: item for item in payload["specific_findings"]}
    assert "seven_reported_annual_averages_match_endpoint_means" in findings
    assert "post_2022_issuer_benchmark_switches_to_ncei" in findings
    assert "current_archive_does_not_prove_historical_availability" in findings
    assert any("revision-free point-in-time" in item for item in payload["point_in_time_policy"])
    assert any("2018 or 2019" in item for item in payload["forbidden_calculations"])


def test_evidence_references_are_hash_bound(payload):
    expected = {
        "cctd_bspi_historical_endpoint",
        "shenhua_public_index_history",
        "shenhua_price_cost_transport_bridge",
    }
    refs = {item["id"]: item for item in payload["evidence_refs"]}
    assert set(refs) == expected
    for item in refs.values():
        target = ROOT / item["path"]
        assert target.exists()
        assert _hash(target) == item["sha256"]


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-bspi-annual-report-reconciliation-latest.json").read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads((ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["script_sha256"] == _hash(Path(MODULE.__file__))
    assert manifest["source_sha256s"] == {
        "cctd_bspi_historical_endpoint": MODULE.BSPI_HASH,
    }
    assert manifest["prior_evidence_sha256s"]["shenhua_public_index_history"] == json.loads(
        (ROOT / "runtime/company-research/shenhua-public-index-history-latest.json").read_text(encoding="utf-8")
    )["sha256"]
    assert manifest["prior_evidence_sha256s"]["shenhua_price_cost_transport_bridge"] == json.loads(
        (ROOT / "runtime/company-research/shenhua-2014-2025-price-cost-transport-bridge-latest.json").read_text(encoding="utf-8")
    )["sha256"]
