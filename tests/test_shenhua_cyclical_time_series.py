import hashlib
import json
import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("shenhua_time_series", ROOT / "scripts" / "build_shenhua_cyclical_time_series.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_reviewed_series_is_twelve_raw_years_and_not_a_normalized_input():
    payload = MODULE.build_series()
    rows = payload["series"]

    assert payload["status"] == "multi_year_raw_series_collected_but_not_approved_as_normalized_inputs"
    assert payload["financial_scope_approved"] is False
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert [row["year"] for row in rows] == list(range(2014, 2026))
    assert len(rows) == 12
    by_year = {row["year"]: row for row in rows}
    assert by_year[2015]["parent_attributable_profit_cny"] == 16144000000
    assert by_year[2017]["operating_cash_flow_cny"] == 95152000000
    assert by_year[2022]["parent_attributable_profit_cny"] == 69626000000
    assert by_year[2025]["cash_paid_for_long_term_assets_cny"] == 48398000000
    assert payload["descriptive_stats"]["parent_attributable_profit_cny"]["median"] == 44452000000
    assert payload["descriptive_stats"]["parent_attributable_profit_cny"]["minimum"] == 16144000000
    assert payload["descriptive_stats"]["parent_attributable_profit_cny"]["maximum"] == 69626000000
    assert payload["restatement_observations"][0]["restated_parent_profit_cny"] == 55805000000
    assert "maintenance_and_growth_capex_not_separated" in payload["blockers"]
    assert "normalized_parent_operating_profit" not in payload


def test_every_series_row_has_a_hash_addressed_original_source():
    payload = MODULE.build_series()
    assert len(payload["evidence_refs"]) == 12
    assert all(ref["sha256"] for ref in payload["evidence_refs"])
    assert all(len(ref["pages"]) == 4 for ref in payload["evidence_refs"])
    assert all(len(set(ref["pages"])) >= 2 for ref in payload["evidence_refs"])
    source_2025 = next(ref for ref in payload["evidence_refs"] if ref["id"] == "shenhua_2025_annual_report_pages")
    expected_2025 = hashlib.sha256((ROOT / "runtime/shenhua-2025-official.pdf").read_bytes()).hexdigest()
    assert source_2025["sha256"] == expected_2025
