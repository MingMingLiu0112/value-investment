"""Build a primary-source research package from China Shenhua's 2025 annual report."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime" / "shenhua-2025-official.pdf"
OUT = ROOT / "runtime" / "company-research" / "shenhua-2025-business-evidence-20260921"
SOURCE_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033004060_c.pdf"


def main() -> None:
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    payload = {
        "symbol": "601088",
        "as_of_period": "2025-12-31",
        "source_type": "exchange_filed_issuer_annual_report",
        "source_url": SOURCE_URL,
        "status": "primary_facts_for_research_not_cyclical_valuation_approval",
        "facts": {
            "operating_revenue_cny": "294916000000",
            "operating_revenue_growth_pct": "-13.2",
            "operating_profit_cny": "75532000000",
            "operating_profit_growth_pct": "-13.3",
            "parent_attributable_net_profit_cny": "52849000000",
            "parent_attributable_net_profit_growth_pct": "-5.3",
            "operating_cash_flow_cny": "75059000000",
            "operating_cash_flow_growth_pct": "-17.6",
            "coal_sales_million_tonnes": "430.9",
            "coal_sales_growth_pct": "-6.4",
            "average_coal_sale_price_growth_pct": "-12.1",
            "generation_twh": "220.20",
            "generation_growth_pct": "-3.8",
            "electricity_sales_growth_pct": "-3.9",
            "average_electricity_sale_price_growth_pct": "-4.0",
            "capital_expenditure_cny": "44686000000",
            "planned_capital_expenditure_cny": "38023000000",
        },
        "evidence_refs": [
            {
                "id": "shenhua_2025_official_management_discussion_pages_19_22",
                "path": "runtime/shenhua-2025-official.pdf",
                "sha256": source_hash,
                "pages": [19, 20, 21, 22],
                "unit": "CNY millions except stated operational units",
            },
            {
                "id": "shenhua_2025_official_capex_page_47",
                "path": "runtime/shenhua-2025-official.pdf",
                "sha256": source_hash,
                "page": 47,
                "unit": "CNY hundred millions",
            },
            {
                "id": "shenhua_2025_official_income_statement_pages_156_158",
                "path": "runtime/shenhua-2025-official.pdf",
                "sha256": source_hash,
                "pages": [156, 157, 158],
                "unit": "CNY millions",
            },
            {
                "id": "shenhua_2025_official_cashflow_page_161",
                "path": "runtime/shenhua-2025-official.pdf",
                "sha256": source_hash,
                "page": 161,
                "unit": "CNY millions",
            },
        ],
        "research_limits": [
            "The annual report's description of integrated operations is issuer disclosure, not independent proof of a durable moat.",
            "Reported annual profit and cash flow are current-cycle facts; they do not establish normalized earnings, commodity-price assumptions, resource life, or a valuation range.",
            "This package does not approve a current quote, price bridge, bear/base/bull valuation, position, order, or trade action.",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
