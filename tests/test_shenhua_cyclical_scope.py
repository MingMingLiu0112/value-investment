import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shenhua_cyclical_scope_is_fail_closed_and_source_bound():
    evidence = ROOT / "runtime/company-research/shenhua-cyclical-scope-20260921/evidence.json"
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    source = ROOT / "runtime/shenhua-2025-official.pdf"

    assert payload["status"] == "cyclical_scope_blocked_no_verified_mid_cycle_time_series"
    assert payload["financial_scope_approved"] is False
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["reported_inputs"]["current_parent_attributable_profit_cny"] == "52849000000"
    assert payload["reported_inputs"]["coal_segment_profit_cny"] == "46597000000"
    assert payload["reported_inputs"]["segment_capital_expenditure_cny"] == "44686000000"
    assert payload["reported_inputs"]["china_standard_recoverable_reserves_billion_tonnes"] == "17.31"
    assert payload["reported_inputs"]["self_produced_coal_average_price_cny_per_tonne"] == "472"
    assert payload["allowed_paths"][0]["status"] == "VALUATION_NOT_READY"
    assert "resource_life_in_years_not_disclosed" in payload["blockers"]
    assert {"bear_normalized_parent_operating_profit", "resource_life_years", "ordinary_shares"} <= set(payload["missing_inputs"])
    assert {ref["page"] for ref in payload["evidence_refs"]} == {20, 30, 31, 32, 47, 148, 460, 458}
    assert all(ref["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest() for ref in payload["evidence_refs"])
    assert not any(key in payload["reported_inputs"] for key in ("bear_value", "base_value", "bull_value"))
