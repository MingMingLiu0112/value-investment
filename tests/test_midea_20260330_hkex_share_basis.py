import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "midea_20260330_hkex_share_basis",
    ROOT / "scripts" / "build_midea_20260330_hkex_share_basis.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_hkex_share_basis_pins_announcement_date_facts_without_registering_current_scope():
    payload = MODULE.build_payload()
    source = ROOT / "runtime/midea-hkex-20260330-annual-results.pdf"
    annual_report = ROOT / "runtime/midea-2025-official.pdf"
    pointer = ROOT / "runtime/company-research/midea-20260330-hkex-share-basis-latest.json"
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    evidence = ROOT / pin["path"] / "evidence.json"

    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == pin["sha256"]
    assert payload["symbol"] == "000333"
    assert payload["status"] == "announcement_date_share_basis_disclosed_not_registered"
    assert payload["announcement_date"] == "2026-03-30"
    assert payload["facts"]["page_15_final_dividend_basis"]["repurchased_a_shares_excluded"] == 80412541
    assert payload["facts"]["page_15_final_dividend_basis"]["shares_entitled_to_final_dividend"] == 7522863645
    assert payload["facts"]["page_94_treasury_share_count"]["a_share_treasury_share_count"] == 80412541
    assert payload["facts"]["page_94_treasury_share_count"]["as_of_is_year_end_2025"] is False
    assert payload["facts"]["page_94_treasury_share_count"]["as_of_is_current_valuation_date"] is False
    assert payload["derived_scope"]["announcement_date_treasury_share_count_observable"] is True
    assert payload["derived_scope"]["year_end_2025_treasury_share_count_observable"] is False
    assert payload["share_basis_registered_for_current_valuation"] is False
    assert payload["registered_valuation_inputs"] == {}
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["valuation_approved"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False

    hkex_refs = [ref for ref in payload["evidence_refs"] if ref["id"].startswith("midea_hkex_")]
    assert {tuple(ref["pages"]) for ref in hkex_refs} == {(1,), (15,), (94,)}
    assert all(ref["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest() for ref in hkex_refs)
    annual_ref = next(ref for ref in payload["evidence_refs"] if ref["id"] == "midea_2025_annual_report_share_scope")
    assert annual_ref["sha256"] == hashlib.sha256(annual_report.read_bytes()).hexdigest()


def test_hkex_share_basis_keeps_announcement_scope_separate_from_fcff_unlock():
    payload = MODULE.build_payload()

    assert any("2026-03-30" in item for item in payload["blocked_uses"])
    assert any("2026-09-22" in item for item in payload["blocked_uses"])
    assert any("unlock FCFF" in item for item in payload["blocked_uses"])
    assert "financial_business_carve_out_and_fcff_enterprise_bridge_still_not_ready" in payload["blockers"]
    assert payload["registered_valuation_model"] is None
    assert "bear" not in payload
    assert "base" not in payload
    assert "bull" not in payload
