import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shenhua_2025_business_evidence_is_primary_source_bound_and_not_a_valuation():
    evidence = ROOT / "runtime/company-research/shenhua-2025-business-evidence-20260921/evidence.json"
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    source = ROOT / "runtime/shenhua-2025-official.pdf"

    assert payload["status"] == "primary_facts_for_research_not_cyclical_valuation_approval"
    assert payload["facts"]["operating_cash_flow_cny"] == "75059000000"
    assert payload["facts"]["coal_sales_growth_pct"] == "-6.4"
    assert payload["facts"]["average_coal_sale_price_growth_pct"] == "-12.1"
    assert {19, 20, 21, 22} == set(payload["evidence_refs"][0]["pages"])
    assert all(ref["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
               for ref in payload["evidence_refs"])
    assert any("not establish normalized earnings" in limit for limit in payload["research_limits"])
