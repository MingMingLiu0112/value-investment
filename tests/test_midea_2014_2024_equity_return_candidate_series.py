import hashlib
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "midea_equity_return_candidate_series",
    ROOT / "scripts" / "build_midea_2014_2024_equity_return_candidate_series.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def payload():
    return MODULE.build()


def test_candidate_series_is_complete_and_fail_closed(payload):
    assert payload["engineering_status"] == "equity_return_candidate_series_compiled"
    assert payload["status"] == "equity_return_candidate_series_compiled_not_reviewed_or_registered"
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["registered_valuation_model"] is None
    assert payload["registered_valuation_inputs"] == {}
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert [row["year"] for row in payload["series"]] == list(range(2014, 2025))
    assert all(row["model_input"] is None for row in payload["series"])


def test_key_attributable_facts_are_pinned(payload):
    by_year = {row["year"]: row for row in payload["series"]}

    assert by_year[2014]["audited_facts"]["attributable_ordinary_equity_cny"] == "39470499840"
    assert by_year[2014]["audited_facts"]["attributable_ordinary_net_profit_cny"] == "10502220260"
    assert by_year[2014]["audited_facts"]["cash_dividend_proposed_cny"] == "4215808472.00"
    assert by_year[2015]["audited_facts"]["distribution_share_base_shares"] == "4267391228"
    assert by_year[2018]["audited_facts"]["buyback_cash_counted_as_distribution_cny"] == "4000000000.00"
    assert by_year[2021]["audited_facts"]["buyback_cash_counted_as_distribution_cny"] == "13664103513.72"
    assert by_year[2024]["audited_facts"]["attributable_ordinary_equity_cny"] == "216750057000"
    assert by_year[2024]["audited_facts"]["attributable_ordinary_net_profit_cny"] == "38537237000"
    assert by_year[2024]["audited_facts"]["cash_dividend_proposed_cny"] == "26711662411.00"


def test_descriptive_payout_ratios_are_separate_from_model_inputs(payload):
    by_year = {row["year"]: row for row in payload["series"]}

    assert Decimal(by_year[2014]["derived_candidates"]["cash_dividend_to_parent_net_profit"]).quantize(Decimal("0.0001")) == Decimal("0.4014")
    assert Decimal(by_year[2019]["derived_candidates"]["cash_dividend_to_parent_net_profit"]).quantize(Decimal("0.0001")) == Decimal("0.4598")
    assert Decimal(by_year[2020]["derived_candidates"]["total_cash_distribution_to_parent_net_profit"]).quantize(Decimal("0.0001")) == Decimal("0.5057")
    assert Decimal(by_year[2021]["derived_candidates"]["buyback_cash_to_parent_net_profit"]).quantize(Decimal("0.0001")) == Decimal("0.4782")
    assert Decimal(by_year[2024]["derived_candidates"]["cash_dividend_to_parent_net_profit"]).quantize(Decimal("0.0001")) == Decimal("0.6931")
    assert by_year[2014]["disclosed_ratios"]["cash_dividend_payout_ratio_in_original_report"] == "40.14%"
    assert by_year[2021]["disclosed_ratios"]["cash_dividend_payout_ratio_in_original_report"] is None
    assert all(row["model_input"] is None for row in payload["series"])


def test_point_in_time_and_later_comparative_buyback_are_separate(payload):
    observations = {item["id"]: item for item in payload["later_comparative_observations"]}
    by_year = {row["year"]: row for row in payload["series"]}

    assert by_year[2019]["audited_facts"]["buyback_cash_counted_as_distribution_cny"] == "0.00"
    assert by_year[2019]["disclosed_ratios"]["total_cash_distribution_ratio_in_original_report"] == "45.98%"
    assert observations["2020_report_restates_2019_buyback_other_cash_distribution"]["comparative_source_page"] == 58
    assert observations["2020_report_restates_2019_buyback_other_cash_distribution"]["values"]["buyback_cash_cny"] == "3200000000.00"
    assert observations["2020_report_restates_2019_buyback_other_cash_distribution"]["values"]["total_cash_distribution_ratio_disclosed"] == "59.19%"
    assert observations["2024_report_comparative_cash_dividend_payout_ratios"]["values"]["2023_cash_dividend_payout_ratio_disclosed"] == "61.63%"


def test_evidence_references_are_hash_addressable_and_page_scoped(payload):
    by_year = {row["year"]: row for row in payload["series"]}
    refs = {ref["id"]: ref for ref in payload["evidence_refs"]}

    assert refs["midea_2014_annual_report_equity_return_pages"]["pages"] == [90, 91, 36, 37]
    assert refs["midea_2024_annual_report_equity_return_pages"]["pages"] == [157, 158, 83, 84]
    for row in payload["series"]:
        ref = refs[f"midea_{row['year']}_annual_report_equity_return_pages"]
        source = ROOT / ref["path"]
        assert _hash(source) == ref["sha256"]
        assert ref["pages"][0] == row["page_refs"]["balance_sheet"]
        assert ref["pages"][1] == row["page_refs"]["income_statement"]


def test_generated_pointer_and_manifest_match_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/midea-2014-2024-equity-return-candidate-latest.json").read_text(encoding="utf-8")
    )
    target = (ROOT / pointer["path"] / "evidence.json").resolve()
    manifest = json.loads((ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["script_sha256"] == _hash(Path(MODULE.__file__))
    assert len(manifest["source_sha256s"]) == 11
