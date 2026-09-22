import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_distribution_capacity", ROOT / "scripts/build_moutai_distribution_capacity_evidence.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_distribution_package_is_history_not_a_cash_capacity_approval():
    payload = MODULE.build()

    assert payload["status"] == "distribution_history_verified_but_forward_cash_capacity_not_approved"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert payload["payout_history"][0]["fiscal_year"] == 2015
    assert payload["payout_history"][-1]["fiscal_year"] == 2025


def test_historical_payout_ratios_are_reproduced_from_pinned_disclosures():
    payload = MODULE.build()
    by_year = {row["fiscal_year"]: row for row in payload["payout_history"]}

    assert by_year[2015]["total_cash_to_parent_eps"] == "0.500029"
    assert by_year[2021]["distribution_type"] == "ordinary_only"
    assert by_year[2022]["distribution_type"] == "ordinary_plus_special_or_interim"
    assert by_year[2024]["total_cash_per_share_cny"] == "51.555"
    assert by_year[2024]["total_cash_to_parent_eps"] == "0.751069"
    assert by_year[2025]["distribution_type"] == "proposed_annual_plus_implemented_interim"
    assert by_year[2025]["total_cash_to_parent_eps"] == "0.790274"


def test_registered_75_percent_payout_is_bounded_but_not_promoted():
    payload = MODULE.build()
    payout = payload["model_payout_assumption"]

    assert payout["registered_payout_ratio"] == "0.75"
    assert payout["registered_stresses"] == ["0.50", "0.85"]
    assert payout["latest_fy2025_cash_dividend_to_consolidated_profit"] == "0.790004"
    assert payout["latest_three_year_cash_dividend_to_average_profit"] == "0.753506"
    assert "future payout commitment" in payout["boundary"]
    assert "does not by itself increase valuation confidence" in payload["assumption_effect"]


def test_parent_cash_capacity_distinguishes_full_year_and_seasonal_half_year():
    payload = MODULE.build()
    capacity = payload["parent_cash_capacity"]

    assert capacity["fy2025"]["coverage"] == "1.224135"
    assert capacity["h1_2026"]["cfo_after_capex_coverage"] == "0.410928"
    assert capacity["h1_2026"]["cfo_plus_investment_income_after_capex_coverage"] == "0.413813"
    assert capacity["h1_2026"]["subsidiary_investment_income_received_cny"] == "101052220.78"
    assert "remittance timing" in capacity["interpretation"]


def test_financial_subsidiary_cash_is_explicitly_excluded():
    payload = MODULE.build()
    boundary = payload["financial_subsidiary_boundary"]

    assert boundary["external_deposits_cny"] == "25426316668.17"
    assert boundary["disclosed_restricted_cash_subset_cny"] == "8358830124.37"
    assert "not freely available parent-company cash" in boundary["rule"]
    assert "financial_subsidiary_cash_is_not_freely_distributable_parent_cash" in payload["blockers"]


def test_primary_report_references_are_hash_addressable_and_page_scoped():
    payload = MODULE.build()
    references = {ref["id"]: ref for ref in payload["evidence_refs"]}

    annual = ROOT / references["moutai_fy2025_annual_report"]["path"]
    interim = ROOT / references["moutai_2026_h1_report"]["path"]
    assert references["moutai_fy2025_annual_report"]["pages"] == [2, 33, 63, 66, 67]
    assert references["moutai_2026_h1_report"]["pages"] == [35, 36]
    assert references["moutai_fy2025_annual_report"]["sha256"] == hashlib.sha256(annual.read_bytes()).hexdigest()
    assert references["moutai_2026_h1_report"]["sha256"] == hashlib.sha256(interim.read_bytes()).hexdigest()


def test_generated_pointer_stays_under_project_root():
    pointer = json.loads((ROOT / "runtime/company-research/600519-distribution-capacity-evidence-latest.json").read_text())
    target = (ROOT / pointer["path"] / "evidence.json").resolve()
    assert target.is_relative_to(ROOT.resolve())
