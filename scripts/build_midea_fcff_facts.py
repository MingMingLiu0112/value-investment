"""Create a partial, evidence-backed FCFF facts package from Midea's retained filing."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime" / "midea-2025-official.pdf"
OUT = ROOT / "runtime" / "company-research" / "midea-fcff-facts-20260922"
POINTER = ROOT / "runtime" / "company-research" / "midea-fcff-facts-latest.json"


def main() -> None:
    sha256 = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    payload = {
        "symbol": "000333", "as_of_period": "2025-12-31", "basis": "2025 consolidated cash-flow statement",
        "package_version": "midea-fcff-facts-v2",
        "financial_scope_approved": False,
        "fcff_inputs": {"capex": "11141889000", "ebit": None, "cash_tax_rate": None,
                        "depreciation": None, "working_capital_change": None, "wacc": None,
                        "net_debt": None, "non_operating_assets": None, "shares": None},
        "observed_facts": {
            "operating_cash_flow_cny": "53345930000",
            "capex_cash_outflow_cny": "11141889000",
            "cash_and_cash_equivalents_cny": "85247150000",
            "short_term_borrowings_cny": "43904550000",
            "current_portion_noncurrent_liabilities_cny": "5821777000",
            "long_term_borrowings_cny": "12658843000",
            "bonds_payable_cny": "3194774000",
            "lease_liabilities_cny": "1901053000",
            "issued_share_capital": "7597145346",
            "fy2025_weighted_ordinary_shares_thousand": "7559265",
            "fy2025_diluted_ordinary_shares_thousand": "7608132",
            "year_end_treasury_stock_carrying_value_cny": "8151117",
            "income_tax_expense_cny": "8565147000",
            "profit_before_tax_cny": "53085343000",
            "consolidated_operating_profit_candidate_cny": "52978773000",
            "finance_income_cny": "2211331000",
            "finance_expense_cny": "8444301000",
            "consolidated_depreciation_and_amortization_candidate_cny": "9339695000",
            "operating_receivable_items_change_cny": "-8112158000",
            "operating_payable_items_change_cny": "11316620000",
        },
        "evidence_refs": [{"id": "midea_2025_official_cashflow_page_137",
                           "path": "runtime/midea-2025-official.pdf", "sha256": sha256,
                           "page": 137, "unit": "CNY thousands"},
                          {"id": "midea_2025_official_balance_sheet_pages_132_133",
                           "path": "runtime/midea-2025-official.pdf", "sha256": sha256,
                           "pages": [132, 133], "unit": "CNY thousands"},
                          {"id": "midea_2025_official_tax_page_230",
                           "path": "runtime/midea-2025-official.pdf", "sha256": sha256,
                           "page": 230, "unit": "CNY thousands"},
                          {"id": "midea_2025_official_share_scope_page_143",
                           "path": "runtime/midea-2025-official.pdf", "sha256": sha256,
                           "page": 143, "unit": "shares"},
                          {"id": "midea_2025_official_income_statement_page_135",
                           "path": "runtime/midea-2025-official.pdf", "sha256": sha256,
                           "page": 135, "unit": "CNY thousands"},
                          {"id": "midea_2025_official_cashflow_reconciliation_page_234",
                           "path": "runtime/midea-2025-official.pdf", "sha256": sha256,
                           "page": 234, "unit": "CNY thousands"}],
        "per_share_blockers": ["fy2025_accounting_weighted_denominator_disclosed_but_not_current_valuation_denominator",
                                "year_end_treasury_share_count_not_disclosed",
                                "current_A_H_valuation_share_scope_not_registered",
                                "financial_fact_sources_not_independently_verified"],
        "blockers": ["Consolidated operating profit is recorded as a candidate only; FCFF EBIT requires financial-business and non-operating-item scope reconciliation",
                     "Cash-tax rate, depreciation/amortization and working-capital changes are recorded only at consolidated level and need FCFF-scope reconciliation",
                     "Financial-business cash, deposits and liabilities prevent direct use of consolidated cash less debt as FCFF net debt",
                     "FY2025 accounting weighted denominator is disclosed but is not a current valuation denominator; the year-end treasury share count is not disclosed"],
        "status": "partial_facts_not_valuation_ready",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (OUT / "manifest.json").write_text(json.dumps({
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "evidence_sha256": digest,
        "source_sha256": sha256,
    }, indent=2), encoding="utf-8")
    POINTER.write_text(json.dumps({"path": str(OUT.relative_to(ROOT)), "sha256": digest}, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(target), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
