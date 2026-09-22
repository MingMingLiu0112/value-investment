"""Compile Shenhua's official cyclical-input candidates without approving them."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime" / "shenhua-2025-official.pdf"
SOURCE_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033004060_c.pdf"
SCOPE = ROOT / "runtime" / "company-research" / "shenhua-cyclical-scope-20260921" / "evidence.json"
SERIES = ROOT / "runtime" / "company-research" / "shenhua-cyclical-time-series-20260921" / "evidence.json"
OUT = ROOT / "runtime" / "company-research" / "shenhua-cyclical-candidate-inputs-20260921"

SOURCE_HASH = "460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc"


def source_ref(ref_id: str, page: int, description: str, unit: str = "CNY millions") -> dict:
    return {"id": ref_id, "path": "runtime/shenhua-2025-official.pdf",
            "sha256": SOURCE_HASH, "page": page, "unit": unit, "description": description}


def page_text(reader: PdfReader, page: int, expected: tuple[str, ...]) -> str:
    text = reader.pages[page - 1].extract_text() or ""
    missing = [value for value in expected if value not in text]
    if missing:
        raise ValueError(f"Page {page} does not contain expected evidence {missing!r}")
    return text


def decimal_ratio(numerator: int, denominator: int) -> str:
    return format(Decimal(numerator) / Decimal(denominator), ".12f")


def build() -> dict:
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_HASH:
        raise ValueError("Shenhua 2025 source hash mismatch")

    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    series = json.loads(SERIES.read_text(encoding="utf-8"))
    reader = PdfReader(str(SOURCE))

    page_text(reader, 329, ("货币资金", "96,772", "流动资产合计"))
    page_text(reader, 331, ("短期借款", "409", "一年内到期的非流动负债", "9,364"))
    page_text(reader, 332, ("长期借款", "28,268", "租赁负债", "971"))
    page_text(reader, 334, ("母公司资产负债表", "83,347"))
    page_text(reader, 335, ("一年内到期的非流动负债", "1,458", "长期借款", "150", "租赁负债", "38"))
    page_text(reader, 428, ("当期所得税费用", "16,511", "17,507"))
    page_text(reader, 429, ("会计利润", "79,339", "82,928"))
    page_text(reader, 455, ("货币资金", "41,247", "76,258"))
    page_text(reader, 31, ("JORC标准下本集团的煤炭可售储量为111.3", "煤炭保有可采储量", "173.1"))
    page_text(reader, 47, ("自产煤单位生产成本", "同比下降 4.8"))
    page_text(reader, 460, ("折旧和摊销费用", "24,842", "报告分部资本开支", "44,686"))
    page_text(reader, 152, ("股本", "19,869", "归属于母公司股东权益合计", "409,107"))
    page_text(reader, 458, ("发行股份及支付现金", "股权过户均已完成", "发行 A 股股份募集配套资金"))

    # Raw balance-sheet working-capital bridge. This deliberately excludes cash,
    # trading assets, short debt and the current portion of long-term debt. It is
    # not a verified normalized mid-cycle input.
    current_operating_assets = {
        2024: 3036 + 12569 + 1174 + 6544 + 2302 + 12666 + 7701,
        2025: 5618 + 13225 + 1495 + 6509 + 2910 + 11850 + 8590,
    }
    current_operating_liabilities = {
        2024: 146 + 38815 + 75 + 4001 + 8253 + 9125 + 17219 + 4151,
        2025: 337 + 41176 + 28 + 3810 + 8199 + 9145 + 12948 + 3846,
    }
    raw_working_capital_change = (
        (current_operating_assets[2025] - current_operating_assets[2024])
        - (current_operating_liabilities[2025] - current_operating_liabilities[2024])
    )

    consolidated_interest_bearing_debt_proxy = 409 + 9364 + 28268 + 971
    consolidated_net_cash_proxy = 96772 - consolidated_interest_bearing_debt_proxy
    parent_reported_net_cash_proxy = 83347 - 1458 - 150 - 38

    jorc_life = Decimal("11.13") / Decimal("0.3321")
    china_recoverable_life = Decimal("17.31") / Decimal("0.3321")

    payload = {
        "symbol": "601088",
        "as_of_period": "2025-12-31",
        "source_type": "exchange_filed_annual_report_cyclical_candidate_input_compilation",
        "source_url": SOURCE_URL,
        "package_version": "shenhua-cyclical-candidate-inputs-v1",
        "status": "cyclical_candidate_inputs_compiled_not_reviewed_or_approved",
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "purpose": (
            "The package turns selected official disclosures into transparent candidate "
            "derivations and records which model inputs remain impossible to derive from "
            "the retained filing. No candidate is fed to the shared valuation model and no "
            "bear/base/bull, bridge, margin, position or order is produced."
        ),
        "model_contract_observations": [
            (
                "The shared model subtracts cash tax from "
                "'normalized_parent_operating_profit', so that input must be a pre-tax "
                "parent-attributable operating profit."
            ),
            (
                "The 2025 report discloses consolidated pre-tax profit and parent net profit, "
                "but the retained pages do not disclose the required parent pre-tax "
                "operating-profit allocation. Parent net profit therefore cannot be used as "
                "a drop-in model input without an audited tax-allocation bridge."
            ),
            (
                "Period-end share capital is not the current valuation denominator because "
                "a post-balance acquisition involved newly issued A shares and further "
                "placement work remained in progress at the report date."
            ),
        ],
        "candidate_derivations": {
            "cash_tax_rate": {
                "status": "unverified_historical_candidate",
                "source_observations": {
                    "current_income_tax_2025_cny_millions": 16511,
                    "pretax_profit_2025_cny_millions": 79339,
                    "current_income_tax_2024_restated_cny_millions": 17507,
                    "pretax_profit_2024_restated_cny_millions": 82928,
                },
                "arithmetic": "current income tax / pre-tax profit",
                "candidate_values": {
                    "2025": decimal_ratio(16511, 79339),
                    "2024_restated": decimal_ratio(17507, 82928),
                    "two_year_average": format((Decimal(16511) / Decimal(79339) + Decimal(17507) / Decimal(82928)) / 2, ".12f"),
                },
                "model_input": None,
                "review_requirement": "Reconstruct cash taxes over a full commodity cycle and reconcile deferred tax and minority allocations before use.",
                "evidence_refs": [
                    source_ref("shenhua_tax_expense_page_428", 428, "Current and deferred income-tax expense detail"),
                    source_ref("shenhua_tax_reconciliation_page_429", 429, "Statutory-rate tax reconciliation and pre-tax profit"),
                ],
            },
            "maintenance_capex": {
                "status": "range_only_no_reviewed_split",
                "source_observations": {
                    "segment_depreciation_and_amortization_cny_millions": 24842,
                    "segment_capital_expenditure_excluding_mining_rights_cny_millions": 44686,
                    "cash_paid_for_long_term_assets_cny_millions": 48398,
                },
                "arithmetic": "D&A is an accounting proxy, not a disclosed maintenance-capital split",
                "candidate_values": {
                    "accounting_depreciation_proxy_cny": "24842000000",
                    "reported_segment_capex_upper_bound_cny": "44686000000",
                    "cash_capex_upper_bound_cny": "48398000000",
                },
                "model_input": None,
                "review_requirement": "Obtain an audited maintenance/growth capex split, ideally by asset and operating unit, and test against a multi-year asset-replacement plan.",
                "evidence_refs": [source_ref("shenhua_segment_capex_page_460", 460, "Segment D&A and segment capital expenditure")],
            },
            "normalized_working_capital_change": {
                "status": "raw_balance_sheet_candidate_not_normalized",
                "source_observations": {
                    "operating_current_assets_2024_cny_millions": current_operating_assets[2024],
                    "operating_current_assets_2025_cny_millions": current_operating_assets[2025],
                    "operating_current_liabilities_2024_cny_millions": current_operating_liabilities[2024],
                    "operating_current_liabilities_2025_cny_millions": current_operating_liabilities[2025],
                },
                "arithmetic": "delta(operating current assets) - delta(operating current liabilities)",
                "candidate_values": {"raw_change_cny": str(raw_working_capital_change * 1000000)},
                "model_input": None,
                "review_requirement": "Reconcile intercompany balances, non-cash items and the 2025 business combination before treating this as normalized cash absorption.",
                "evidence_refs": [
                    source_ref("shenhua_current_assets_page_329", 329, "Consolidated current assets"),
                    source_ref("shenhua_current_liabilities_page_331", 331, "Consolidated current liabilities"),
                ],
            },
            "resource_life_years": {
                "status": "reserve_over_current_output_range_candidate",
                "source_observations": {
                    "jorc_marketable_reserves_billion_tonnes": "11.13",
                    "china_standard_recoverable_reserves_billion_tonnes": "17.31",
                    "self_produced_coal_2025_billion_tonnes": "0.3321",
                },
                "arithmetic": "reserve tonnage / 2025 self-produced coal output",
                "candidate_values": {
                    "jorc_over_current_output_years": format(jorc_life, ".12f"),
                    "china_recoverable_over_current_output_years": format(china_recoverable_life, ".12f"),
                },
                "model_input": None,
                "review_requirement": "Choose reserve standard, model production decline, recoveries and future output, then state a mine/portfolio service life instead of a static ratio.",
                "evidence_refs": [source_ref("shenhua_reserve_page_31", 31, "China-standard and JORC reserve disclosures")],
            },
            "net_cash_attributable_to_parent": {
                "status": "unverified_reported_surface_proxies",
                "source_observations": {
                    "consolidated_cash_cny_millions": 96772,
                    "consolidated_interest_bearing_debt_proxy_cny_millions": consolidated_interest_bearing_debt_proxy,
                    "consolidated_net_cash_proxy_cny_millions": consolidated_net_cash_proxy,
                    "parent_cash_cny_millions": 83347,
                    "parent_reported_net_cash_proxy_cny_millions": parent_reported_net_cash_proxy,
                    "consolidated_cash_at_finance_company_cny_millions": 41247,
                },
                "arithmetic": "reported cash minus listed debt-like rows; no minority, restricted-cash or intercompany allocation",
                "candidate_values": {
                    "consolidated_reported_net_cash_proxy_cny": str(consolidated_net_cash_proxy * 1000000),
                    "parent_reported_net_cash_proxy_cny": str(parent_reported_net_cash_proxy * 1000000),
                },
                "model_input": None,
                "review_requirement": "Allocate cash and debt between parent, minority interests and finance-company balances, remove restricted and trapped cash, and update for post-balance acquisition consideration.",
                "evidence_refs": [
                    source_ref("shenhua_consolidated_balance_sheet_pages_329_332", 329, "Consolidated cash and debt-like rows"),
                    source_ref("shenhua_consolidated_noncurrent_debt_page_332", 332, "Consolidated long-term borrowings and lease liabilities"),
                    source_ref("shenhua_parent_balance_sheet_pages_334_335", 334, "Parent cash and debt-like rows"),
                    source_ref("shenhua_parent_noncurrent_debt_page_335", 335, "Parent current maturity, borrowings and lease liabilities"),
                    source_ref("shenhua_related_party_cash_page_455", 455, "Finance-company deposits and related-party balances"),
                ],
            },
            "ordinary_shares": {
                "status": "period_end_value_not_current_denominator",
                "source_observations": {
                    "period_end_share_capital_cny_millions": 19869,
                    "post_balance_acquisition_share_issuance": True,
                    "related_placement_still_in_progress": True,
                },
                "candidate_values": {},
                "model_input": None,
                "review_requirement": "Reconcile A/H shares after the completed acquisition issuance and the then-outstanding placement; confirm treasury and weighted-basis requirements.",
                "evidence_refs": [
                    source_ref("shenhua_share_capital_page_152", 152, "Period-end share capital"),
                    source_ref("shenhua_post_balance_events_page_458", 458, "Post-balance acquisition and share issuance"),
                ],
            },
            "normalized_parent_operating_profit": {
                "status": "cannot_derive_from_retained_disclosure",
                "source_observations": {
                    "consolidated_pretax_profit_2025_cny_millions": 79339,
                    "parent_net_profit_2025_cny_millions": 52849,
                    "parent_pretax_operating_profit": None,
                },
                "candidate_values": {},
                "model_input": None,
                "review_requirement": "Construct a parent pre-tax operating-profit bridge from audited parent statements or an independently reviewed tax and minority allocation; no historical median or current low PE may stand in for it.",
                "evidence_refs": [
                    source_ref("shenhua_income_statement_page_337", 337, "Consolidated pre-tax profit and income tax"),
                    source_ref("shenhua_parent_net_profit_page_338", 338, "Parent net profit and minority profit"),
                ],
            },
            "unit_cost": {
                "status": "change_only_no_absolute_cost_curve",
                "source_observations": {"self_produced_coal_unit_cost_change_pct_2025": "-4.8"},
                "candidate_values": {},
                "model_input": None,
                "review_requirement": "Recover an absolute multi-year unit-cost series and compare it with peers or a defensible industry cost curve.",
                "evidence_refs": [source_ref("shenhua_2026_targets_page_47", 47, "Unit-cost change and 2026 target")],
            },
            "discount_rate_long_term_growth": {
                "status": "no_company_specific_reviewed_basis",
                "source_observations": {},
                "candidate_values": {},
                "model_input": None,
                "review_requirement": "Select a documented cost of equity for the listed parent and an evidence-backed real terminal-growth assumption; generic values are not an approval.",
                "evidence_refs": [],
            },
        },
        "unresolved_model_inputs": [
            "bear_normalized_parent_operating_profit",
            "base_normalized_parent_operating_profit",
            "bull_normalized_parent_operating_profit",
            "discount_rate",
            "long_term_growth",
            "net_cash_attributable_to_parent",
            "ordinary_shares",
            "trough_parent_operating_profit",
            "unit_cost",
        ],
        "blockers": [
            "parent_pretax_operating_profit_allocation_not_disclosed",
            "ordinary_share_denominator_changed_after_period_end",
            "attributable_net_cash_and_restricted_cash_not_allocated",
            "maintenance_and_growth_capex_split_not_disclosed",
            "working_capital_change_is_raw_not_normalized",
            "resource_life_is_a_static_ratio_not_a_reviewed_life",
            "absolute_unit_cost_curve_not_available",
            "discount_rate_and_terminal_growth_have_no_reviewed_basis",
            "no_candidate_is_approved_as_a_model_input",
        ],
        "linked_evidence": [
            {
                "id": "shenhua_cyclical_scope",
                "path": SCOPE.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(SCOPE.read_bytes()).hexdigest(),
                "status": scope["status"],
            },
            {
                "id": "shenhua_cyclical_time_series",
                "path": SERIES.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(SERIES.read_bytes()).hexdigest(),
                "status": series["status"],
            },
        ],
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
    }
    return payload


def main() -> int:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "evidence_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "source_sha256": SOURCE_HASH,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime" / "company-research" / "shenhua-cyclical-candidate-inputs-latest.json"
    pointer.write_text(json.dumps({
        "path": OUT.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                      "status": payload["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
