import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_midea_ebit_scope_fails_closed_without_financial_business_carve_out():
    facts = ROOT / "runtime/company-research/midea-ebit-scope-20260921/evidence.json"
    payload = json.loads(facts.read_text(encoding="utf-8"))
    source = ROOT / "runtime/midea-2025-official.pdf"

    assert payload["status"] == "ebit_scope_blocked_no_verifiable_financial_business_carve_out"
    assert payload["financial_scope_approved"] is False
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["reported_inputs"]["consolidated_operating_profit_cny"] == "52978773000"
    assert payload["finance_business_disclosure"]["interest_income_cny"] == "2050168000"
    assert payload["finance_business_disclosure"]["standalone_balance_sheet_disclosed"] is False
    assert payload["finance_business_disclosure"]["standalone_profit_and_loss_disclosed"] is False
    assert payload["segment_disclosure"]["industrial_ebit_directly_observable"] is False
    assert {path["id"] for path in payload["allowed_paths"]} == {
        "industrial_fcff_carve_out", "consolidated_enterprise_value_bridge",
    }
    assert {ref["page"] for ref in payload["evidence_refs"]} == {135, 225, 227, 229, 234, 249, 250}
    assert all(ref["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
               for ref in payload["evidence_refs"])
    assert "bear_value" not in payload and "base_value" not in payload and "bull_value" not in payload
