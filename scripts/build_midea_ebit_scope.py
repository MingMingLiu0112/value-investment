"""Audit Midea's 2025 EBIT scope and financial-business carve-out boundaries."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime" / "midea-2025-official.pdf"
OUT = ROOT / "runtime" / "company-research" / "midea-ebit-scope-20260921"


def main() -> None:
    sha256 = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    payload = {
        "symbol": "000333",
        "as_of_period": "2025-12-31",
        "source_type": "issuer_annual_report_financial_statement_scope_audit",
        "status": "ebit_scope_blocked_no_verifiable_financial_business_carve_out",
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "scope_conclusion": (
            "Consolidated FCFF is not applicable until standalone financial-business "
            "statements or an audited enterprise-value bridge can allocate industrial "
            "operating profit, tax, debt, cash and working capital to the listed-equity claim."
        ),
        "reported_inputs": {
            "total_operating_revenue_cny": "458502407000",
            "operating_revenue_excluding_finance_business_cny": "456451731000",
            "consolidated_operating_profit_cny": "52978773000",
            "consolidated_profit_before_tax_cny": "53085343000",
            "non_finance_finance_income_net_cny": "5903546000",
            "depreciation_and_amortization_cny": "9339695000",
        },
        "finance_business_disclosure": {
            "interest_income_cny": "2050168000",
            "handling_fee_income_cny": "508000",
            "interest_expense_cny": "275000",
            "handling_fee_expense_cny": "1642000",
            "standalone_balance_sheet_disclosed": False,
            "standalone_profit_and_loss_disclosed": False,
            "segment_location": "other_segment",
            "other_segment_mix": [
                "industrial_robotics_and_automation",
                "logistics_automation",
                "supply_chain_services",
                "green_energy_and_storage",
                "financial_services",
                "medical_products_and_services",
            ],
        },
        "non_operating_or_financing_items": {
            "other_income_cny": "2664313000",
            "investment_income_cny": "1694661000",
            "fair_value_change_gain_cny": "782358000",
            "credit_impairment_loss_cny": "355860000",
            "asset_impairment_loss_cny": "1156469000",
            "asset_disposal_loss_cny": "76024000",
        },
        "segment_disclosure": {
            "report_segments": ["smart_home", "building_technology", "industrial_technology", "other"],
            "other_segment_profit_cny": "2603866000",
            "total_segment_profit_cny": "49425794000",
            "other_profit_or_loss_cny": "3659549000",
            "industrial_ebit_directly_observable": False,
            "industrial_invested_capital_directly_observable": False,
        },
        "allowed_paths": [
            {
                "id": "industrial_fcff_carve_out",
                "status": "MODEL_NOT_APPLICABLE",
                "reason": (
                    "The annual report does not disclose standalone financial-business profit, "
                    "balance sheet, tax, debt, cash or working capital; financial services are "
                    "mixed with robotics, energy and medical businesses in the other segment."
                ),
            },
            {
                "id": "consolidated_enterprise_value_bridge",
                "status": "VALUATION_NOT_READY",
                "reason": (
                    "A bridge requires separately evidenced value for the financial business and "
                    "non-operating assets before consolidated FCFF can be converted to the "
                    "listed-equity claim."
                ),
            },
        ],
        "blockers": [
            "financial_business_profit_and_balance_sheet_not_separately_disclosed",
            "industrial_debt_cash_tax_and_working_capital_not_allocated",
            "other_segment_mixes_financial_services_with_non_financial_businesses",
            "reported_operating_profit_contains_financial_and_non_operating_items",
        ],
        "evidence_refs": [
            {"id": "midea_2025_official_income_statement_page_135", "path": "runtime/midea-2025-official.pdf",
             "sha256": sha256, "page": 135, "unit": "CNY thousands"},
            {"id": "midea_2025_official_financial_business_interest_note_page_225", "path": "runtime/midea-2025-official.pdf",
             "sha256": sha256, "page": 225, "unit": "CNY thousands"},
            {"id": "midea_2025_official_non_finance_finance_income_page_227", "path": "runtime/midea-2025-official.pdf",
             "sha256": sha256, "page": 227, "unit": "CNY thousands"},
            {"id": "midea_2025_official_investment_and_fair_value_page_229", "path": "runtime/midea-2025-official.pdf",
             "sha256": sha256, "page": 229, "unit": "CNY thousands"},
            {"id": "midea_2025_official_cashflow_reconciliation_page_234", "path": "runtime/midea-2025-official.pdf",
             "sha256": sha256, "page": 234, "unit": "CNY thousands"},
            {"id": "midea_2025_official_segment_definition_page_249", "path": "runtime/midea-2025-official.pdf",
             "sha256": sha256, "page": 249, "unit": "disclosure"},
            {"id": "midea_2025_official_segment_report_page_250", "path": "runtime/midea-2025-official.pdf",
             "sha256": sha256, "page": 250, "unit": "CNY thousands"},
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
