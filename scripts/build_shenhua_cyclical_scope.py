"""Audit China Shenhua's 2025 cyclical-normalization evidence boundary."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime" / "shenhua-2025-official.pdf"
OUT = ROOT / "runtime" / "company-research" / "shenhua-cyclical-scope-20260921"
SOURCE_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033004060_c.pdf"


def ref(ref_id: str, page: int, unit: str) -> dict:
    return {"id": ref_id, "path": "runtime/shenhua-2025-official.pdf", "page": page, "unit": unit}


def main() -> None:
    sha256 = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    payload = {
        "symbol": "601088",
        "as_of_period": "2025-12-31",
        "source_type": "exchange_filed_issuer_annual_report_cyclical_scope_audit",
        "source_url": SOURCE_URL,
        "status": "cyclical_scope_blocked_no_verified_mid_cycle_time_series",
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "scope_conclusion": (
            "A normalized-resource valuation requires a verified mid-cycle profit, cash, capex, "
            "cost and price series, an explicit resource life and trough-solvency test. The 2025 "
            "annual report supplies strong current-cycle segment and reserve facts but does not "
            "by itself establish those forward-looking mid-cycle inputs."
        ),
        "reported_inputs": {
            "current_parent_attributable_profit_cny": "52849000000",
            "current_operating_cash_flow_cny": "75059000000",
            "total_report_segment_profit_cny": "79339000000",
            "coal_segment_profit_cny": "46597000000",
            "power_segment_profit_cny": "12627000000",
            "railway_segment_profit_cny": "12901000000",
            "port_segment_profit_cny": "2631000000",
            "shipping_segment_profit_cny": "269000000",
            "chemical_segment_profit_cny": "58000000",
            "unallocated_segment_profit_cny": "4275000000",
            "segment_depreciation_and_amortization_cny": "24842000000",
            "segment_capital_expenditure_cny": "44686000000",
            "total_assets_cny": "627761000000",
            "total_liabilities_cny": "146310000000",
            "parent_equity_cny": "409107000000",
            "minority_equity_cny": "72344000000",
            "cash_cny": "96772000000",
            "short_borrowings_cny": "409000000",
            "long_borrowings_cny": "28268000000",
            "lease_liabilities_cny": "971000000",
            "share_capital_cny": "19869000000",
            "china_standard_resource_base_billion_tonnes": "41.41",
            "china_standard_recoverable_reserves_billion_tonnes": "17.31",
            "jorc_marketable_reserves_billion_tonnes": "11.13",
            "self_produced_coal_million_tonnes": "332.1",
            "self_produced_coal_average_price_cny_per_tonne": "472",
            "self_produced_coal_unit_cost_change_pct": "-4.8",
            "annual_long_term_contract_volume_pct": "53.2",
            "monthly_long_term_contract_volume_pct": "39.4",
            "spot_volume_pct": "3.8",
            "proposed_dividend_per_share_cny": "1.03",
            "proposed_dividend_total_cny": "22340000000",
        },
        "missing_inputs": {
            "bear_normalized_parent_operating_profit": "No independently verified multi-year mid-cycle profit series or commodity-price envelope is registered.",
            "base_normalized_parent_operating_profit": "The current annual report reports only 2025 versus restated 2024, not a reviewed full-cycle baseline.",
            "bull_normalized_parent_operating_profit": "No evidence-backed upside commodity-price and cost envelope is registered.",
            "cash_tax_rate": "A normalized effective cash-tax rate has not been reconstructed from official tax disclosures.",
            "maintenance_capex": "The report discloses total capital expenditure but does not split maintenance from growth capital.",
            "normalized_working_capital_change": "No verified mid-cycle working-capital series has been reconciled.",
            "discount_rate": "No reviewed cost-of-equity or WACC basis is attached to this resource claim.",
            "long_term_growth": "No evidence-backed long-term real growth assumption is registered.",
            "resource_life_years": "Reserve tonnage is disclosed, but annual report does not state mine service life in years.",
            "net_cash_attributable_to_parent": "Consolidated cash, debt and minority interests are not allocated to the listed-parent common-equity claim.",
            "ordinary_shares": "Period-end share capital is disclosed, but the exact ordinary-share denominator still requires a dedicated share-basis reconciliation.",
            "trough_parent_operating_profit": "A historical or stressed trough profit point has not been independently verified.",
            "unit_cost": "The report discloses a unit-cost change but not an independently comparable absolute cost curve or peer position.",
        },
        "allowed_paths": [
            {
                "id": "cyclical_normalized_equity",
                "status": "VALUATION_NOT_READY",
                "reason": (
                    "The shared model may run only after all missing mid-cycle, resource-life, "
                    "net-cash and share-bridge inputs are verified. Low current PE or high current "
                    "profit does not substitute for normalized earnings."
                ),
            }
        ],
        "blockers": [
            "mid_cycle_profit_cash_capex_and_price_series_not_verified",
            "resource_life_in_years_not_disclosed",
            "maintenance_and_growth_capex_not_separated",
            "attributable_net_cash_and_share_basis_not_reconciled",
            "independent_cost_curve_and_trough_solvency_not_established",
            "no_market_price_or_execution_input_is_used_here",
        ],
        "evidence_refs": [
            {"sha256": sha256, **ref("shenhua_2025_official_key_operations_page_20", 20, "CNY hundred millions and operational units")},
            {"sha256": sha256, **ref("shenhua_2025_official_coal_pricing_pages_30_31", 30, "CNY millions, million tonnes, CNY/tonne")},
            {"sha256": sha256, **ref("shenhua_2025_official_resource_disclosure_pages_31_32", 31, "hundred million tonnes")},
            {"sha256": sha256, **ref("shenhua_2025_official_segment_results_pages_32_41", 32, "CNY millions")},
            {"sha256": sha256, **ref("shenhua_2025_official_capex_page_47", 47, "CNY hundred millions")},
            {"sha256": sha256, **ref("shenhua_2025_official_balance_sheet_pages_148_152", 148, "CNY millions")},
            {"sha256": sha256, **ref("shenhua_2025_official_segment_report_page_460", 460, "CNY millions")},
            {"sha256": sha256, **ref("shenhua_2025_official_post_balance_dividend_page_458", 458, "CNY per share and millions")},
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
