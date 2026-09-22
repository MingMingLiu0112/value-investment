import hashlib
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_attributable_profit_series",
    ROOT / "scripts" / "build_shenhua_2014_2025_attributable_profit_series.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def payload():
    return MODULE.build()


def test_attributable_profit_series_is_source_bound_and_fail_closed(payload):
    assert payload["engineering_status"] == "attributable_profit_tax_candidate_series_complete"
    assert payload["status"] == "attributable_profit_and_tax_candidate_series_compiled_not_reviewed_or_approved"
    assert payload["financial_scope_approved"] is False
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert payload["registered_cyclical_facts_operating_inputs"] == []
    assert [row["year"] for row in payload["series"]] == list(range(2014, 2026))


def test_audited_income_and_cash_tax_values_are_pinned(payload):
    by_year = {row["year"]: row for row in payload["series"]}

    assert by_year[2015]["audited_facts"]["parent_attributable_net_profit_cny_millions"] == 16_144
    assert by_year[2015]["audited_facts"]["cash_taxes_paid_cny_millions"] == 37_480
    assert by_year[2022]["audited_facts"]["parent_attributable_net_profit_cny_millions"] == 69_626
    assert by_year[2025]["audited_facts"]["parent_attributable_net_profit_cny_millions"] == 52_849
    assert by_year[2025]["audited_facts"]["income_tax_expense_cny_millions"] == 16_556
    assert by_year[2025]["audited_facts"]["minority_net_profit_cny_millions"] == 9_934

    assert by_year[2015]["derived_candidates"]["cash_taxes_paid_to_pretax_profit_rate"] == "1.132942386"
    assert by_year[2025]["derived_candidates"]["cash_taxes_paid_to_pretax_profit_rate"] == "0.474382082"


def test_pro_forma_is_inside_the_no_tax_allocation_bounds(payload):
    for row in payload["series"]:
        candidate = Decimal(row["derived_candidates"]["parent_attributable_pretax_operating_profit_uniform_share_pro_forma_cny_millions"])
        lower = Decimal(row["derived_candidates"]["parent_attributable_pretax_operating_profit_no_tax_assumption_lower_cny_millions"])
        upper = Decimal(row["derived_candidates"]["parent_attributable_pretax_operating_profit_no_tax_assumption_upper_cny_millions"])
        assert lower <= candidate <= upper
        assert row["model_input"] is None


def test_restatements_are_separated_from_original_filings(payload):
    observations = {item["id"]: item for item in payload["restatement_observations"]}
    assert "2015_report_restated_2014" in observations
    assert "2023_report_restated_2022" in observations
    assert "2025_report_restated_2024" in observations
    assert observations["2025_report_restated_2024"]["values"]["2024_parent_profit_original"] == 58_671
    assert observations["2025_report_restated_2024"]["values"]["2024_parent_profit_restated_in_2025"] == 55_805


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-2014-2025-attributable-profit-series-latest.json").read_text(encoding="utf-8")
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

    payload = json.loads(target.read_text(encoding="utf-8"))
    for row in payload["series"]:
        source_hash = manifest["source_sha256s"][row["source_id"]]
        source = next(item for item in payload["evidence_refs"] if item["id"].startswith(f"shenhua_{row['year']}_"))
        assert source["sha256"] == source_hash
        assert _hash(ROOT / source["path"]) == source_hash
