"""Build the Gree mature-manufacturing FCFF valuation package.

The industrial operating scope is separated from treasury/financial assets and
debt.  The result is low-confidence conditional research and stays
action=no_order; no current quote is claimed for this symbol.
"""
from __future__ import annotations

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "config" / "m1-valuation-packages-v1" / "000651-fcff.json"

SYMBOL = "000651"
NAME = "格力电器"
ANNUAL_ID = "gree_fy2025_annual"
INTERIM_ID = "gree_2026h1"
COST_EQUITY_ID = "china_cost_equity_20260923"

ANNUAL_PATH = (
    "runtime/company-research/m1-valuation-filings-20260923/000651/"
    "2025-12-31-annual-9afdfdd459e8bca7be30fdcc32e333e9759b0b44737e8464b2cb64a8978022e3.pdf"
)
ANNUAL_SHA256 = "7cc972f2d199e2ec3797cc5da479e8268afa59b77875770de3bcd3648242fb8c"
INTERIM_PATH = (
    "runtime/company-research/m1-valuation-filings-20260923/000651/"
    "2026-06-30-interim-1eecac2793533cffcfe4bef5f7ef434aef9b5661a8015cc2880cdedcebb0cf4a.pdf"
)
INTERIM_SHA256 = "50da2e03fddbe9dd424d8fe7881f47fb34efa5d38c96aa9449c12e445c3b2dec"
COST_EQUITY_PATH = (
    "runtime/valuation-research/china-cost-of-equity-m1-20260923/evidence.json"
)
COST_EQUITY_SHA256 = "aed2b12ef4f9cd16e08f9962782b73d3709aa2d4cf94d89549728233aa5a27a7"

INDUSTRIAL_EBIT_2025 = "28839181614.31"
CASH_TAX_RATE = "0.15"
DEPRECIATION = "5054584486.97"
INDUSTRIAL_CAPEX_2025 = "1717311068.10"
WORKING_CAPITAL_INCREASE_2025 = "-4965811678.62"
WACC = "0.085"
ORDINARY_SHARES = "5601405741"

NET_DEBT = "71744407416.55"
NON_OPERATING_ASSETS = "238298832557.32"
MINORITY_INTEREST = "3861982870.68"

ANNUAL_REF = {
    "id": ANNUAL_ID,
    "path": ANNUAL_PATH,
    "sha256": ANNUAL_SHA256,
}
INTERIM_REF = {
    "id": INTERIM_ID,
    "path": INTERIM_PATH,
    "sha256": INTERIM_SHA256,
}
COST_EQUITY_REF = {
    "id": COST_EQUITY_ID,
    "path": COST_EQUITY_PATH,
    "sha256": COST_EQUITY_SHA256,
}


def annual_evidence() -> list[dict[str, str]]:
    return [{"id": ANNUAL_ID}]


def joint_evidence() -> list[dict[str, str]]:
    return [{"id": ANNUAL_ID}, {"id": INTERIM_ID}]


def bridge() -> list[dict[str, object]]:
    return [
        {
            "name": "cash_and_liquid_financial_assets",
            "kind": "nonoperating_asset",
            "value": "153186167311.92",
            "exposure_ids": [
                "gree_cash",
                "gree_trading_financial_assets",
                "gree_receivables_financing",
                "gree_buyback_resale",
            ],
            "evidence_refs": [ANNUAL_ID],
        },
        {
            "name": "longer_term_financial_assets",
            "kind": "nonoperating_asset",
            "value": "84752161911.55",
            "exposure_ids": [
                "gree_one_year_noncurrent",
                "gree_other_current_financial",
                "gree_other_debt_investments",
                "gree_loans",
                "gree_long_term_equity",
                "gree_other_equity",
                "gree_other_noncurrent_financial",
            ],
            "evidence_refs": [ANNUAL_ID],
        },
        {
            "name": "investment_property",
            "kind": "nonoperating_asset",
            "value": "360503333.85",
            "exposure_ids": ["gree_investment_property"],
            "evidence_refs": [ANNUAL_ID],
        },
        {
            "name": "interest_bearing_debt",
            "kind": "debt",
            "value": NET_DEBT,
            "exposure_ids": ["gree_debt"],
            "evidence_refs": [ANNUAL_ID],
        },
        {
            "name": "minority_interest",
            "kind": "minority",
            "value": MINORITY_INTEREST,
            "exposure_ids": ["gree_minority"],
            "evidence_refs": [ANNUAL_ID],
        },
    ]


def forecast(
    years: list[int],
    ebits: list[str],
    capex: list[str],
    working_capital: list[str],
) -> list[dict[str, object]]:
    return [
        {
            "year": years[index],
            "ebit": ebits[index],
            "cash_tax_rate": CASH_TAX_RATE,
            "depreciation": DEPRECIATION,
            "capex": capex[index],
            "working_capital_increase": working_capital[index],
            "wacc": WACC,
            "evidence_refs": [ANNUAL_ID, INTERIM_ID],
        }
        for index in range(len(years))
    ]


def scenario(
    ebits: list[str],
    terminal_next_year_nopat: str,
    terminal_roic: str,
    capex: list[str],
    working_capital: list[str],
) -> dict[str, object]:
    return {
        "forecast": forecast(
            [2026, 2027, 2028, 2029, 2030],
            ebits,
            capex,
            working_capital,
        ),
        "terminal": {
            "next_year_nopat": terminal_next_year_nopat,
            "growth": "0.02",
            "roic": terminal_roic,
            "wacc": WACC,
            "evidence_refs": [ANNUAL_ID, COST_EQUITY_ID],
        },
        "bridge": bridge(),
        "operating_exposure_ids": ["gree_industrial_operations"],
        "ordinary_shares": ORDINARY_SHARES,
        "share_evidence_refs": [ANNUAL_ID],
        "currency": "CNY",
    }


SCENARIOS = {
    "bear": scenario(
        ["24000000000", "23000000000", "22000000000", "21000000000", "20000000000"],
        "17000000000",
        "0.06",
        ["2500000000", "3000000000", "3000000000", "3000000000", "3000000000"],
        ["-4965811678.62", "-2000000000", "-1000000000", "0", "1000000000"],
    ),
    "base": scenario(
        ["28839181614.31", "28500000000", "28500000000", "28500000000", "28500000000"],
        "24225000000",
        "0.09",
        ["1717311068.10", "2500000000", "3000000000", "3000000000", "3000000000"],
        ["-4965811678.62", "-1000000000", "0", "0", "0"],
    ),
    "bull": scenario(
        ["32000000000", "33000000000", "34000000000", "35000000000", "35000000000"],
        "29750000000",
        "0.12",
        ["1717311068.10", "2500000000", "3000000000", "3500000000", "3500000000"],
        ["-4965811678.62", "-3000000000", "-2000000000", "-1000000000", "0"],
    ),
}


def assumption(
    name: str,
    unit: str,
    bear: str,
    base: str,
    bull: str,
    basis: str,
    rationale: str,
    evidence: list[dict[str, str]],
    ordering: str = "ascending",
) -> dict[str, object]:
    return {
        "name": name,
        "unit": unit,
        "bear": bear,
        "base": base,
        "bull": bull,
        "basis": basis,
        "rationale": rationale,
        "confidence": "low",
        "sensitivity": "high",
        "evidence_refs": evidence,
        "blockers": [],
        "ordering": ordering,
    }


ASSUMPTIONS = [
    assumption(
        "wacc",
        "decimal",
        WACC,
        WACC,
        WACC,
        "generic mature-manufacturing WACC proxy from dated China cost-of-equity evidence",
        "No issuer-specific credit spread or market-derived company WACC is claimed.",
        [{"id": COST_EQUITY_ID}],
    ),
    assumption(
        "cash_tax_rate",
        "decimal",
        CASH_TAX_RATE,
        CASH_TAX_RATE,
        CASH_TAX_RATE,
        "bounded effective tax rate below the consolidated statutory range",
        "Industrial tax is held as a simple rate; no deferred or cash-tax schedule is modelled.",
        annual_evidence(),
    ),
    assumption(
        "depreciation",
        "cny",
        DEPRECIATION,
        DEPRECIATION,
        DEPRECIATION,
        "FY2025 consolidated cash-flow supplement fixed-asset, investment-property, right-of-use and intangible amortization",
        "The audited D&A sum is held flat because industrial and financial-scope depreciation are not separately disclosed.",
        annual_evidence(),
    ),
    assumption(
        "forecast_ebit_2026",
        "cny",
        "24000000000",
        "28839181614.31",
        "32000000000",
        "FY2025 industrial revenue less industrial operating costs, excluding finance and investment income",
        "Explicit bounds only; the consolidated financial-business scope is excluded from operating EBIT.",
        joint_evidence(),
    ),
    assumption(
        "forecast_ebit_2030",
        "cny",
        "20000000000",
        "28500000000",
        "35000000000",
        "Bounded terminal-year continuation from the 2026 scenario",
        "The final explicit year converges to terminal economics without a claimed point forecast.",
        joint_evidence(),
    ),
    assumption(
        "forecast_capex_2026",
        "cny",
        "2500000000",
        INDUSTRIAL_CAPEX_2025,
        "1717311068.10",
        "FY2025 audited purchase of fixed/intangible/long-term assets with scenario bounds",
        "Maintenance versus growth capex has not been separately verified.",
        annual_evidence(),
        "descending",
    ),
    assumption(
        "forecast_capex_2030",
        "cny",
        "3000000000",
        "3000000000",
        "3500000000",
        "Bounded continuation of future reinvestment intensity",
        "Higher bull-scenario capex reflects industrial expansion, not a prediction.",
        annual_evidence(),
    ),
    assumption(
        "working_capital_increase_2026",
        "cny",
        WORKING_CAPITAL_INCREASE_2025,
        WORKING_CAPITAL_INCREASE_2025,
        WORKING_CAPITAL_INCREASE_2025,
        "FY2025 audited inventory, receivable and payable changes, excluding the large restricted-cash reconciliation item",
        "The observable working-capital release is applied once and then scenario changes decay.",
        annual_evidence(),
    ),
    assumption(
        "working_capital_increase_2030",
        "cny",
        "1000000000",
        "0",
        "0",
        "Bounded terminal-year working-capital change",
        "Finance-scope receivables and restricted cash remain unresolved.",
        annual_evidence(),
        "descending",
    ),
    assumption(
        "terminal_next_year_nopat",
        "cny",
        "17000000000",
        "24225000000",
        "29750000000",
        "Terminal-year industrial EBIT after the simple tax proxy",
        "Terminal NOPAT is derived mechanically from the final explicit-year bound.",
        joint_evidence(),
    ),
    assumption(
        "terminal_growth",
        "decimal",
        "0.02",
        "0.02",
        "0.02",
        "Long-run nominal growth bound below WACC",
        "No company-specific high-growth terminal path is assumed.",
        [{"id": COST_EQUITY_ID}],
    ),
    assumption(
        "terminal_roic",
        "decimal",
        "0.06",
        "0.09",
        "0.12",
        "Bounded terminal incremental returns across mature consumer-industrial economics",
        "Issuer ROIC and incremental ROIC remain unverified.",
        annual_evidence(),
    ),
]


def binding(
    assumption_name: str,
    scenario_name: str,
    field_path: str,
    expected_value: str,
    evidence: list[dict[str, str]],
) -> dict[str, object]:
    return {
        "assumption_name": assumption_name,
        "scenario": scenario_name,
        "field_path": field_path,
        "expected_value": expected_value,
        "evidence_refs": evidence,
    }


def scenario_binding(
    name: str,
    scenario_name: str,
    path: str,
    value: str,
) -> dict[str, object]:
    return binding(name, scenario_name, path, value, joint_evidence())


BINDINGS: list[dict[str, object]] = []
for scenario_name, values in SCENARIOS.items():
    first = values["forecast"][0]
    last = values["forecast"][-1]
    terminal = values["terminal"]
    BINDINGS.extend(
        [
            scenario_binding("wacc", scenario_name, "forecast.0.wacc", WACC),
            scenario_binding(
                "cash_tax_rate",
                scenario_name,
                "forecast.0.cash_tax_rate",
                CASH_TAX_RATE,
            ),
            scenario_binding(
                "depreciation",
                scenario_name,
                "forecast.0.depreciation",
                DEPRECIATION,
            ),
            scenario_binding(
                "forecast_ebit_2026",
                scenario_name,
                "forecast.0.ebit",
                str(first["ebit"]),
            ),
            scenario_binding(
                "forecast_ebit_2030",
                scenario_name,
                "forecast.4.ebit",
                str(last["ebit"]),
            ),
            scenario_binding(
                "forecast_capex_2026",
                scenario_name,
                "forecast.0.capex",
                str(first["capex"]),
            ),
            scenario_binding(
                "forecast_capex_2030",
                scenario_name,
                "forecast.4.capex",
                str(last["capex"]),
            ),
            scenario_binding(
                "working_capital_increase_2026",
                scenario_name,
                "forecast.0.working_capital_increase",
                str(first["working_capital_increase"]),
            ),
            scenario_binding(
                "working_capital_increase_2030",
                scenario_name,
                "forecast.4.working_capital_increase",
                str(last["working_capital_increase"]),
            ),
            scenario_binding(
                "terminal_next_year_nopat",
                scenario_name,
                "terminal.next_year_nopat",
                str(terminal["next_year_nopat"]),
            ),
            scenario_binding(
                "terminal_growth",
                scenario_name,
                "terminal.growth",
                "0.02",
            ),
            scenario_binding(
                "terminal_roic",
                scenario_name,
                "terminal.roic",
                str(terminal["roic"]),
            ),
        ]
    )


def payload() -> dict[str, object]:
    return {
        "schema_version": "m1-valuation-package-v1",
        "package_version": "20260923.1",
        "descriptor_version": "000651-m1-valuation-v1",
        "symbol": SYMBOL,
        "name": NAME,
        "profile_id": "mature_manufacturing",
        "requested_model": "fcff",
        "run_id": "000651-m1-valuation-20260923",
        "point_in_time": {
            "report_period": "2026-06-30",
            "research_as_of": "2026-09-22",
            "valuation_date": "2026-09-22",
            "available_at": "2026-09-23T09:00:00+08:00",
            "computed_at": "2026-09-23T09:10:00+08:00",
        },
        "dependencies": {
            "rule_version": "m1-valuation-rules-v1",
            "model_id": "fcff",
            "model_version": "fcff-shared-scenario-v1",
            "parser_version": "pdfium-m1-20260923",
            "scan_watermark": "cninfo-event-scan-2026-09-22",
        },
        "sources": [
            {
                "id": ANNUAL_ID,
                "kind": "official_issuer_filing",
                "location": ANNUAL_PATH,
                "sha256": ANNUAL_SHA256,
                "published_at": "2026-04-28T16:00:00+00:00",
                "retrieved_at": "2026-09-23T00:52:00+00:00",
                "parser_version": "pdfium-m1-20260923",
            },
            {
                "id": INTERIM_ID,
                "kind": "official_issuer_filing",
                "location": INTERIM_PATH,
                "sha256": INTERIM_SHA256,
                "published_at": "2026-08-27T16:00:00+00:00",
                "retrieved_at": "2026-09-23T00:52:00+00:00",
                "parser_version": "pdfium-m1-20260923",
            },
            {
                "id": COST_EQUITY_ID,
                "kind": "valuation_reference",
                "location": COST_EQUITY_PATH,
                "sha256": COST_EQUITY_SHA256,
                "retrieved_at": "2026-09-23T00:53:00+00:00",
                "parser_version": "valuation-evidence-v1",
            },
        ],
        "research_case": {
            "symbol": SYMBOL,
            "name": NAME,
            "as_of": "2026-09-22",
            "run_id": "000651-m1-valuation-20260923",
            "generated_at": "2026-09-23T08:00:00+08:00",
            "research_version": "000651-m1-valuation-v1",
            "industry": "家用电器",
            "investment_path": "成熟制造 / 品牌渠道与金融资产混业",
            "thesis": "空调品牌、渠道和制造效率支持稳定工业现金回报，但海外下滑、国内价格带下移以及财务公司/受限资金规模要求把工业 FCFF 与金融资产严格拆分后才能讨论估值。",
            "return_driver": "消费电器结构优化、工业制品第二曲线和经营现金转换；同时受行业需求、海外策略与金融业务资金占用影响。",
            "mispricing_hypothesis": "未证明市场系统性低估。当前只检验低置信度工业 FCFF 与账面金融资产拆分后的权益价值区间，不形成任何价格结论。",
            "financial_summary": {
                "period_end": "2026-06-30",
                "revenue_2025_cny": "170447058533.57",
                "parent_profit_2025_cny": "29003103411.66",
                "parent_equity_2025_cny": "145929297804.02",
                "weighted_roe_2025": "0.1988",
                "h1_2026_parent_profit_yoy": "-0.0787",
            },
            "positives": [
                {
                    "kind": "fact",
                    "text": "FY2025 合并工业营业收入 1,704.47 亿元，归母净利润 290.03 亿元，归母净资产 1,459.29 亿元。",
                    "evidence_refs": [ANNUAL_ID],
                },
                {
                    "kind": "fact",
                    "text": "FY2025 经营活动现金流净额 463.83 亿元，资本开支仅 17.17 亿元，工业现金流转换能力可观察。",
                    "evidence_refs": [ANNUAL_ID],
                },
                {
                    "kind": "fact",
                    "text": "2026H1 主营业务收入占营业收入 95.37%、同比提升 5.47 个百分点，净利率 14.81%。",
                    "evidence_refs": [INTERIM_ID],
                },
            ],
            "counter_evidence": [
                {
                    "kind": "fact",
                    "text": "2026H1 营业总收入同比 -8.14%，归母净利润 -7.87%，外销主营业务收入 -21.98%。",
                    "evidence_refs": [INTERIM_ID],
                },
                {
                    "kind": "fact",
                    "text": "2026H1 国内家用空调出货端/零售端销量同比 -5.6%/-13.1%，2,100 元以下机型零售占比升至 54.45%。",
                    "evidence_refs": [INTERIM_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "短期借款、财务公司、受限现金和大量金融资产使合并报表不能直接作为工业 FCFF；现金充沛本身不能证明金融资产可按账面价值回收。",
                    "evidence_refs": [ANNUAL_ID, INTERIM_ID],
                },
            ],
            "thesis_breakers": [
                {
                    "kind": "hypothesis",
                    "text": "若国内价格带继续下移或海外收入继续明显下滑，工业 EBIT 情景需要下调。",
                    "evidence_refs": [INTERIM_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若财务公司、受限资金、金融资产和短期借款的法人层级拆分仍不可得，工业/金融资产桥接不能解锁。",
                    "evidence_refs": [ANNUAL_ID, INTERIM_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若渠道库存、合同负债或经营现金流出现不可持续波动，工业现金转换质量需要撤回。",
                    "evidence_refs": [ANNUAL_ID, INTERIM_ID],
                },
            ],
            "next_events": [
                {
                    "kind": "fact",
                    "text": "观察下一份法定财务报告中的收入、分部毛利率、经营现金流、合同负债、库存、金融资产和短期借款。",
                    "evidence_refs": [INTERIM_ID],
                },
                {
                    "kind": "gap",
                    "text": "补充财务公司、受限资金、融资负债、金融资产公允价值和法人层级现金流后再做正式人工批准。",
                    "evidence_refs": [INTERIM_ID],
                },
            ],
            "evidence_status": "verified",
            "valuation_status": "not_ready",
            "research_status": "financial_scope_approved",
            "blockers": [
                "formal G3 human valuation approval not present",
                "treasury/financial company scope and restricted cash remain unresolved",
                "issuer-specific beta, credit spread and market-derived WACC remain unverified",
                "ROIC and incremental ROIC remain unverified",
                "H1 2026 interim report is unaudited",
            ],
            "evidence_refs": [ANNUAL_REF, INTERIM_REF, COST_EQUITY_REF],
            "quote_date": None,
            "financial_period": "2026-06-30",
            "missing_date_reasons": {
                "quote_date": "no archived quote session for 000651; production quote is pending external data"
            },
        },
        "facts": {
            "kind": "fcff",
            "symbol": SYMBOL,
            "as_of": "2026-09-22",
            "verified": True,
            "confidence": "低",
            "evidence_refs": [ANNUAL_REF, INTERIM_REF],
            "blockers": [],
            "operating_inputs": {
                "ebit": INDUSTRIAL_EBIT_2025,
                "cash_tax_rate": CASH_TAX_RATE,
                "depreciation": DEPRECIATION,
                "capex": INDUSTRIAL_CAPEX_2025,
                "working_capital_change": WORKING_CAPITAL_INCREASE_2025,
                "wacc": WACC,
                "net_debt": NET_DEBT,
                "non_operating_assets": NON_OPERATING_ASSETS,
                "shares": ORDINARY_SHARES,
            },
            "scenario_inputs": SCENARIOS,
        },
        "assumptions": {
            "evidence_refs": [ANNUAL_REF, INTERIM_REF, COST_EQUITY_REF],
            "assumptions": ASSUMPTIONS,
            "blockers": [],
        },
        "assumption_bindings": BINDINGS,
        "quote": None,
        "model_validity_input": {
            "model_id": "fcff-shared-scenario-v1",
            "valid_from": "2026-09-22",
            "events": [],
            "event_scan_evidence_refs": [
                {
                    "id": INTERIM_ID,
                    "path": INTERIM_PATH,
                    "sha256": INTERIM_SHA256,
                    "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-27/1225515004.PDF",
                }
            ],
            "blockers": [],
        },
        "blockers": [
            "G3 human approval pending",
            "treasury/financial company scope and restricted cash remain unresolved",
            "valuation is conditional_research_only and must never imply a buy decision",
        ],
    }


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(str(OUTPUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
