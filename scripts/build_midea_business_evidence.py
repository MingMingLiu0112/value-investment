"""Build primary-source business evidence for the Midea research case."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime" / "midea-2025-official.pdf"
OUT = ROOT / "runtime" / "company-research" / "midea-business-evidence-20260921"


def main() -> None:
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    payload = {
        "symbol": "000333",
        "as_of_period": "2025-12-31",
        "source_type": "issuer_annual_report_primary_disclosure",
        "status": "business_facts_for_research_not_valuation_approval",
        "facts": {
            "operating_revenue_cny": "456451731000",
            "operating_revenue_growth_pct": "12.11",
            "household_revenue_cny": "299927239000",
            "household_revenue_growth_pct": "11.28",
            "commercial_industrial_revenue_cny": "122752958000",
            "commercial_industrial_revenue_growth_pct": "17.47",
            "household_gross_margin_pct": "29.90",
            "household_gross_margin_change_pct_points": "-0.08",
            "commercial_industrial_gross_margin_pct": "20.81",
            "commercial_industrial_gross_margin_change_pct_points": "-0.58",
            "air_conditioner_volume_growth_pct": "12.89",
            "refrigeration_volume_growth_pct": "2.62",
            "washing_appliance_volume_growth_pct": "-6.17",
            "research_development_expense_cny": "17787624000",
            "research_development_expense_growth_pct": "9.58",
        },
        "evidence_refs": [
            {
                "id": "midea_2025_official_segment_revenue_page_49",
                "path": "runtime/midea-2025-official.pdf",
                "sha256": source_hash,
                "page": 49,
                "unit": "CNY thousands except percentages",
            },
            {
                "id": "midea_2025_official_segment_margin_page_50",
                "path": "runtime/midea-2025-official.pdf",
                "sha256": source_hash,
                "page": 50,
                "unit": "percent and percentage points",
            },
            {
                "id": "midea_2025_official_production_sales_page_51",
                "path": "runtime/midea-2025-official.pdf",
                "sha256": source_hash,
                "page": 51,
                "unit": "percent",
            },
            {
                "id": "midea_2025_official_expenses_page_52",
                "path": "runtime/midea-2025-official.pdf",
                "sha256": source_hash,
                "page": 52,
                "unit": "CNY thousands except percentages",
            },
        ],
        "research_limits": [
            "Issuer disclosures establish reported operating facts, not independent proof of competitive advantage or management quality.",
            "Segment margin and volume movements require subsequent-period validation before a durable-growth conclusion.",
            "This package does not approve FCFF inputs, per-share values, market-price comparison, or a trading action.",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
