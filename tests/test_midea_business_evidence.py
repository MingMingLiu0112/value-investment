import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_midea_business_evidence_is_primary_source_bound_and_research_only():
    evidence = ROOT / "runtime/company-research/midea-business-evidence-20260921/evidence.json"
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    source = ROOT / "runtime/midea-2025-official.pdf"

    assert payload["status"] == "business_facts_for_research_not_valuation_approval"
    assert payload["facts"]["operating_revenue_growth_pct"] == "12.11"
    assert payload["facts"]["commercial_industrial_gross_margin_change_pct_points"] == "-0.58"
    assert payload["facts"]["washing_appliance_volume_growth_pct"] == "-6.17"
    assert {ref["page"] for ref in payload["evidence_refs"]} == {49, 50, 51, 52}
    assert all(ref["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
               for ref in payload["evidence_refs"])
    assert any("does not approve FCFF" in limit for limit in payload["research_limits"])
