import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_midea_partial_fcff_facts_are_primary_source_bound_and_fail_closed():
    facts = ROOT / "runtime/company-research/midea-fcff-facts-20260922/evidence.json"
    payload = json.loads(facts.read_text(encoding="utf-8"))
    source = ROOT / "runtime/midea-2025-official.pdf"
    assert payload["status"] == "partial_facts_not_valuation_ready"
    assert payload["package_version"] == "midea-fcff-facts-v2"
    assert payload["observed_facts"]["operating_cash_flow_cny"] == "53345930000"
    assert payload["observed_facts"]["capex_cash_outflow_cny"] == "11141889000"
    assert payload["fcff_inputs"]["capex"] == "11141889000"
    assert payload["fcff_inputs"]["ebit"] is None
    assert any(ref.get("page") == 137 for ref in payload["evidence_refs"])
    assert payload["observed_facts"]["consolidated_depreciation_and_amortization_candidate_cny"] == "9339695000"
    assert payload["observed_facts"]["fy2025_weighted_ordinary_shares_thousand"] == "7559265"
    assert payload["observed_facts"]["year_end_treasury_stock_carrying_value_cny"] == "8151117"
    assert any(ref.get("page") == 234 for ref in payload["evidence_refs"])
    assert "weighted_average_ordinary_shares_not_verified" not in payload["per_share_blockers"]
    assert "fy2025_accounting_weighted_denominator_disclosed_but_not_current_valuation_denominator" in payload["per_share_blockers"]
    assert all(ref["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
               for ref in payload["evidence_refs"])
