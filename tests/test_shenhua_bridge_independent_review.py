import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_bridge_independent_review",
    ROOT / "scripts" / "build_shenhua_bridge_independent_review.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def test_independent_review_is_source_bound_and_fail_closed():
    payload = MODULE.build()

    assert payload["engineering_status"] == "bridge_independent_review_complete"
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert payload["registered_cyclical_facts_operating_inputs"] == []

    assert _hash(MODULE.ANNUAL) == MODULE.ANNUAL_HASH
    assert _hash(MODULE.HKEX_INTERIM) == MODULE.HKEX_INTERIM_HASH
    assert _hash(MODULE.CN_INTERIM) == MODULE.CN_INTERIM_HASH

    sources = {item["id"]: item for item in payload["source_documents"]}
    assert set(sources) == {"hkex_2026_interim_full_report", "company_cn_2026_interim_full_report"}
    assert sources["hkex_2026_interim_full_report"]["pdf_pages"] == 155
    assert sources["company_cn_2026_interim_full_report"]["pdf_pages"] == 156


def test_ordinary_share_denominator_is_approved_but_not_yet_registered():
    payload = MODULE.build()
    review = payload["decisions"]["ordinary_shares"]

    assert review["decision"] == "approved_as_point_in_time_ordinary_shares"
    assert review["review_status"] == "approved_point_in_time_denominator"
    assert review["candidate_value"] == 21_689_434_304
    assert review["as_of"] == "2026-06-30"
    assert review["approved_model_input_contract"] == {
        "field": "ordinary_shares",
        "value": 21_689_434_304,
    }
    assert review["registered_in_cyclical_facts_operating_inputs"] is False
    assert any("19,868,519,955" in fact["quoted_facts"][0] for fact in review["evidence_refs"])
    assert any("18,311,952,304" in fact["quoted_facts"][0] for fact in review["evidence_refs"])

    package = ROOT / review["candidate_package"]["path"]
    assert package.exists()
    assert _hash(package) == review["candidate_package"]["sha256"]


def test_profit_and_net_cash_candidates_are_rejected():
    payload = MODULE.build()

    profit = payload["decisions"]["parent_attributable_pretax_operating_profit"]
    assert profit["decision"] == "rejected_for_verified_model_input"
    assert profit["review_status"] == "rejected_for_verified_model_input"
    assert profit["retained_use"] == "dated_unaudited_pro_forma_research_interval_only"
    assert profit["model_input"] is None
    assert "subsidiary-by-subsidiary" in profit["reason"]

    net_cash = payload["decisions"]["net_cash_attributable_to_parent"]
    assert net_cash["decision"] == "rejected_for_model_input"
    assert net_cash["review_status"] == "rejected_for_model_input"
    assert net_cash["retained_use"] == "2025_parent_legal_entity_balance_sheet_interval_only"
    assert net_cash["model_input"] is None
    assert "not financial net cash" in net_cash["reason"]

    for decision in (profit, net_cash):
        package = ROOT / decision["candidate_package"]["path"]
        assert package.exists()
        assert _hash(package) == decision["candidate_package"]["sha256"]


def test_interim_facts_distinguish_working_capital_from_net_cash():
    payload = MODULE.build()
    facts = payload["interim_consolidated_facts_2026_06_30"]

    assert facts["cash_and_cash_equivalents_cny_millions"] == 51_673
    assert facts["restricted_bank_deposits_cny_millions"] == 18_197
    assert facts["time_deposits_over_three_months_cny_millions"] == 65_722
    assert facts["total_borrowings_cny_millions"] == 157_628
    assert facts["minority_interests_cny_millions"] == 99_608
    assert facts["current_net_liabilities_cny_millions"] == 31_619
    assert facts["informational_consolidated_liquid_financial_assets_minus_borrowings_cny_millions"] == -22_036
    assert "not attributable parent net cash" in facts["observation"]


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-2026-bridge-independent-review-latest.json").read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads(
        (ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8")
    )

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["source_sha256"] == {
        "annual_report": MODULE.ANNUAL_HASH,
        "hkex_2026_interim_full_report": MODULE.HKEX_INTERIM_HASH,
        "company_cn_2026_interim_full_report": MODULE.CN_INTERIM_HASH,
    }
    assert set(manifest["reviewed_bridge_sha256"]) == {
        "share_bridge",
        "parent_operating_profit_bridge",
        "attributable_net_cash_bridge",
    }
