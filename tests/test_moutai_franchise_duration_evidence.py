import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_franchise_duration",
    ROOT / "scripts/build_moutai_franchise_duration_evidence.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_franchise_duration_package_is_bounded_not_empirical():
    payload = MODULE.build()

    assert payload["status"] == "bounded_conditional_policy_audited_not_empirical_franchise_duration"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert "not a measurement of future competitive-advantage duration" in payload["scope"].lower()


def test_five_year_fade_is_a_conditional_central_policy():
    payload = MODULE.build()
    policy = payload["central_policy"]

    assert policy["forecast_years"] == 5
    assert policy["fade_years"] == 5
    assert policy["fade_stresses"] == [0, 10]
    assert policy["terminal_roe_policy"] == "cost_of_equity_no_permanent_excess_return"
    assert policy["classification"] == "conditional_central_policy"
    assert "not an empirical competitive-advantage measurement" in policy["why_five_years_is_the_central_policy"]
    assert "lower-bound/absence-of-franchise test" in policy["why_0_and_10_are_stresses"]
    assert "does not establish how long" in policy["boundary"]


def test_zero_and_ten_year_fades_are_explicit_stress_bounds():
    payload = MODULE.build()
    stress = payload["stress_design"]

    assert stress["immediate_fade"]["fade_years"] == 0
    assert stress["immediate_fade"]["role"] == "absence_of_franchise_lower_bound"
    assert stress["immediate_fade"]["conditional_base_value_cny"] == (
        "411.137558948713642745728610928319867382209106451"
    )
    assert stress["central_fade"]["fade_years"] == 5
    assert stress["central_fade"]["role"] == "bounded_conditional_central_policy"
    assert stress["central_fade"]["conditional_base_value_cny"] == (
        "478.433655123709878566799093620973766559693028909"
    )
    assert stress["extended_fade"]["fade_years"] == 10
    assert stress["extended_fade"]["role"] == "materially_longer_duration_upper_bound_stress"
    assert stress["extended_fade"]["conditional_base_value_cny"] == (
        "558.478112741803735009970585857822465286855704610"
    )
    assert "not lower/central/upper evidence about how long" in stress["interpretation"]


def test_issuer_and_peer_counterevidence_are_retained():
    payload = MODULE.build()

    assert payload["issuer_evidence"]["fy2025_volume_price"]["liquor_revenue_growth_pct"] == "-1.08"
    assert payload["issuer_evidence"]["fy2025_volume_price"]["liquor_sales_volume_growth_pct"] == "2.13"
    assert payload["issuer_evidence"]["fy2025_volume_price"]["approximate_revenue_per_tonne_change_pct"] == "-3.1431"
    assert any("not same-year finished-goods sales" in item
               for item in payload["issuer_evidence"]["capacity_and_inventory_constraints"])
    assert payload["peer_counterevidence"]["status"] == "retained_as_counterevidence_not_transferred_to_moutai"
    assert any("operating cash flow was negative" in item for item in payload["peer_counterevidence"]["observations"])


def test_audit_verifies_consistency_without_promoting_the_model():
    payload = MODULE.build()
    checks = payload["policy_consistency"]

    assert checks["forward_assumption_review_passed"] is True
    assert checks["cost_of_equity_review_passed"] is True
    assert checks["primary_scenarios_use_five_year_fade"] is True
    assert checks["immediate_and_ten_year_fade_stresses_present"] is True
    assert checks["terminal_regime_has_no_permanent_excess_return"] is True
    assert checks["reverse_valuation_covers_0_5_10_year_horizons"] is True
    assert checks["reverse_valuation_result"] == "all_horizons_above_registered_envelope"
    assert "manufacture a positive margin" in checks["no_quote_fit_to_create_a_buy_point"]
    assert payload["conclusion"]["effect"].startswith("The franchise-duration policy is now audited as bounded")


def test_primary_and_peer_references_are_hash_addressable_and_page_scoped():
    payload = MODULE.build()
    references = {ref["id"]: ref for ref in payload["evidence_refs"]}

    annual = ROOT / references["moutai_fy2025_annual_report"]["path"]
    interim = ROOT / references["moutai_2026_h1_report"]["path"]
    peer = ROOT / references["wuliangye_peer_interim_pdf"]["path"]
    assert references["moutai_fy2025_annual_report"]["pages"] == [10, 15, 22]
    assert references["moutai_2026_h1_report"]["pages"] == [7]
    assert references["wuliangye_peer_interim_pdf"]["pages"] == [6, 7, 11]
    assert references["moutai_fy2025_annual_report"]["sha256"] == hashlib.sha256(annual.read_bytes()).hexdigest()
    assert references["moutai_2026_h1_report"]["sha256"] == hashlib.sha256(interim.read_bytes()).hexdigest()
    assert references["wuliangye_peer_interim_pdf"]["sha256"] == hashlib.sha256(peer.read_bytes()).hexdigest()


def test_generated_pointer_stays_under_project_root():
    pointer = json.loads(
        (ROOT / "runtime/company-research/600519-franchise-duration-evidence-latest.json").read_text(encoding="utf-8")
    )
    target = (ROOT / pointer["path"] / "evidence.json").resolve()
    assert target.is_relative_to(ROOT.resolve())
    assert hashlib.sha256(target.read_bytes()).hexdigest() == pointer["sha256"]
