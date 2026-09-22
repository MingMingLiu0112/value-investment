import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_2026_share_bridge",
    ROOT / "scripts" / "build_shenhua_2026_share_bridge.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_share_bridge_is_source_bound_and_arithmetically_consistent():
    payload = MODULE.build()

    assert payload["status"] == "share_bridge_compiled_not_reviewed_or_approved"
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False

    annual = ROOT / payload["annual_report"]["path"]
    assert annual.exists()
    assert hashlib.sha256(annual.read_bytes()).hexdigest().upper() == MODULE.ANNUAL_HASH

    source_by_id = {source["id"]: source for source in payload["sources"]}
    assert set(source_by_id) == {"acquisition_result", "placement_result", "interim_summary"}
    for source in source_by_id.values():
        path = ROOT / source["path"]
        assert path.exists()
        assert hashlib.sha256(path.read_bytes()).hexdigest().upper() == source["sha256"]
        assert source["pdf_pages"] > 0
        assert source["url"].endswith(source["path"].rsplit("/", 1)[-1].split("-", 1)[0] + ".PDF")

    period = payload["period_end_2025_12_31"]
    issuance = {item["id"]: item for item in payload["post_balance_issuances"]}
    arithmetic = payload["arithmetic"]
    assert period["ordinary_shares_total"] == 19_868_519_955
    assert period["treasury_shares"] == 0
    assert arithmetic["post_acquisition_total"] == 21_231_768_401
    assert arithmetic["post_placement_total"] == 21_689_434_304
    assert issuance["acquisition_asset_share_issuance"]["new_shares"] == 1_363_248_446
    assert issuance["placement_supplementary_fund_share_issuance"]["new_shares"] == 457_665_903
    assert issuance["acquisition_asset_share_issuance"]["cash_consideration_cny"] == "93518843500.00"
    assert issuance["acquisition_asset_share_issuance"]["total_consideration_cny"] == "133598347800.00"
    assert issuance["acquisition_asset_share_issuance"]["share_consideration_cny"] == "40079504300.00"


def test_share_denominator_remains_an_unapproved_candidate():
    payload = MODULE.build()
    candidate = payload["ordinary_share_denominator_candidate"]

    assert candidate["candidate_value"] == 21_689_434_304
    assert candidate["as_of"] == "2026-06-30"
    assert candidate["review_status"] == "not_reviewed_or_approved"
    assert candidate["model_input"] is None
    assert candidate["weighted_average_shares"] is None
    assert candidate["treasury_adjusted_shares"] is None
    assert candidate["review_requirements"]

    assert payload["interim_corroboration_2026_06_30"]["ordinary_shares_total"] == 21_689_434_304
    assert all(item["restricted_at_registration"] for item in payload["post_balance_issuances"])
    assert any(caveat["id"] == "placement_registration_year_typo" for caveat in payload["source_typo_caveats"])


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-2026-share-bridge-latest.json").read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads(
        (ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8")
    )

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = hashlib.sha256(target.read_bytes()).hexdigest().upper()
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["annual_report_sha256"] == MODULE.ANNUAL_HASH
    assert set(manifest["source_sha256"]) == {
        source["filename"] for source in MODULE.SOURCES
    }
