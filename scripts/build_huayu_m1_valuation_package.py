"""Build the Huayu mature-manufacturing FCFF valuation package.

Official annual/interim facts are kept separate from low-confidence scenario
assumptions.  The generated package remains action=no_order and is not a
production valuation approval.
"""
from __future__ import annotations

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "config" / "m1-valuation-packages-v1" / "600741-fcff.json"

SYMBOL = "600741"
NAME = "华域汽车"
ANNUAL_ID = "huayu_fy2025_annual"
INTERIM_ID = "huayu_2026h1"
COST_EQUITY_ID = "china_cost_equity_20260923"
QUOTE_ID = "huayu_quote_20260922"

ANNUAL_PATH = (
    "runtime/company-research/m1-valuation-filings-20260923/600741/"
    "2025-12-31-annual-fc0c682eeb07cc29ea4201e9113cfa5bb5febf805a3a5ff5eb4dfe1b861ce841.pdf"
)
ANNUAL_SHA256 = "19d879f380cc042f4f5d91cb952c939f95b4e953366e8045da1e3a58760065f4"
INTERIM_PATH = (
    "runtime/company-research/m1-valuation-filings-20260923/600741/"
    "2026-06-30-interim-2b5ced0dc37827ad9d35036fb0d49b3b34e6ff47f2559222db0225f7519162c6.pdf"
)
INTERIM_SHA256 = "77db47cdf18cc46123c4924cb869a75dc3d4404f718e132292e6c9132e65f2f9"
COST_EQUITY_PATH = (
    "runtime/valuation-research/china-cost-of-equity-m1-20260923/evidence.json"
)
COST_EQUITY_SHA256 = "aed2b12ef4f9cd16e08f9962782b73d3709aa2d4cf94d89549728233aa5a27a7"
QUOTE_BUNDLE_PATH = "runtime/quote-sessions/20260923T005634211464Z/bundle.json"
QUOTE_BUNDLE_SHA256 = "5e49dc79bbc0132b040175e993e2f5dd5a3813c7167ade7aa2afc5c51cea19c0"

EBIT_2025 = "6724879712.52"
CASH_TAX_RATE = "0.137"
DEPRECIATION = "6586275313.78"
CAPEX_2025 = "4752057698.59"
WORKING_CAPITAL_INCREASE_2025 = "3213137150.67"
WACC = "0.085"
ORDINARY_SHARES = "3152723984"

NET_DEBT = "17643806194.84"
NON_OPERATING_ASSETS = "59969757947.58"
MINORITY_INTEREST = "3993209722.41"

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
            "name": "cash_and_debt_investments",
            "kind": "nonoperating_asset",
            "value": "42248491420.70",
            "exposure_ids": ["huayu_cash", "huayu_debt_investments"],
            "evidence_refs": ["huayu_fy2025_annual"],
        },
        {
            "name": "long_term_equity_and_other_financial_assets",
            "kind": "nonoperating_asset",
            "value": "17211651633.02",
            "exposure_ids": ["huayu_long_term_equity", "huayu_other_financial"],
            "evidence_refs": ["huayu_fy2025_annual"],
        },
        {
            "name": "investment_property",
            "kind": "nonoperating_asset",
            "value": "509614893.86",
            "exposure_ids": ["huayu_investment_property"],
            "evidence_refs": ["huayu_fy2025_annual"],
        },
        {
            "name": "interest_bearing_debt",
            "kind": "debt",
            "value": NET_DEBT,
            "exposure_ids": ["huayu_debt"],
            "evidence_refs": ["huayu_fy2025_annual"],
        },
        {
            "name": "minority_interest",
            "kind": "minority",
            "value": MINORITY_INTEREST,
            "exposure_ids": ["huayu_minority"],
            "evidence_refs": ["huayu_fy2025_annual"],
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
            "evidence_refs": ["huayu_fy2025_annual", "huayu_2026h1"],
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
            "evidence_refs": ["huayu_fy2025_annual", "china_cost_equity_20260923"],
        },
        "bridge": bridge(),
        "operating_exposure_ids": ["huayu_consolidated_operations"],
        "ordinary_shares": ORDINARY_SHARES,
        "share_evidence_refs": ["huayu_fy2025_annual"],
        "currency": "CNY",
    }


SCENARIOS = {
    "bear": scenario(
        ["5200000000", "4900000000", "4700000000", "4600000000", "4600000000"],
        "3969800000",
        "0.06",
        ["5000000000", "5200000000", "5400000000", "5600000000", "5800000000"],
        ["3213137150.67", "2500000000", "2200000000", "2000000000", "1800000000"],
    ),
    "base": scenario(
        ["6724879712.52", "6700000000", "6700000000", "6750000000", "6800000000"],
        "5868400000",
        "0.08",
        ["4752057698.59", "4900000000", "5000000000", "5000000000", "5000000000"],
        ["3213137150.67", "1500000000", "1200000000", "1000000000", "800000000"],
    ),
    "bull": scenario(
        ["7800000000", "8000000000", "8100000000", "8150000000", "8200000000"],
        "7076600000",
        "0.10",
        ["4600000000", "4800000000", "4900000000", "5000000000", "5000000000"],
        ["3213137150.67", "800000000", "600000000", "400000000", "200000000"],
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
        "FY2025 book effective tax expense divided by pretax profit",
        "The effective rate is used as a bounded proxy, not a cash-tax schedule.",
        annual_evidence(),
    ),
    assumption(
        "depreciation",
        "cny",
        DEPRECIATION,
        DEPRECIATION,
        DEPRECIATION,
        "FY2025 consolidated cash-flow supplement D&A components",
        "The audited D&A sum is held flat and future asset additions are not modelled separately.",
        annual_evidence(),
    ),
    assumption(
        "forecast_ebit_2026",
        "cny",
        "5200000000",
        "6724879712.52",
        "7800000000",
        "FY2025 operating EBIT adjusted for customer-cycle pressure and platform revenue",
        "Explicit bounds only; no high-confidence company profit forecast is asserted.",
        joint_evidence(),
    ),
    assumption(
        "forecast_ebit_2030",
        "cny",
        "4600000000",
        "6800000000",
        "8200000000",
        "Bounded terminal-year continuation from the 2026 scenario",
        "The final explicit year converges to terminal economics without a claimed point forecast.",
        joint_evidence(),
    ),
    assumption(
        "forecast_capex_2026",
        "cny",
        "5000000000",
        CAPEX_2025,
        "4600000000",
        "FY2025 audited capex with bear/base/bull reinvestment bounds",
        "Maintenance versus growth capex has not been separately verified.",
        annual_evidence(),
        "descending",
    ),
    assumption(
        "forecast_capex_2030",
        "cny",
        "5800000000",
        "5000000000",
        "5000000000",
        "Bounded continuation of future reinvestment intensity",
        "Higher bear-scenario capex reflects uncertain transition investment, not a prediction.",
        annual_evidence(),
        "descending",
    ),
    assumption(
        "working_capital_increase_2026",
        "cny",
        WORKING_CAPITAL_INCREASE_2025,
        WORKING_CAPITAL_INCREASE_2025,
        WORKING_CAPITAL_INCREASE_2025,
        "FY2025 audited cash-flow working-capital reconciliation",
        "The observable change is applied once and then scenario-specific changes decay.",
        annual_evidence(),
    ),
    assumption(
        "working_capital_increase_2030",
        "cny",
        "1800000000",
        "800000000",
        "200000000",
        "Bounded terminal-year working-capital change",
        "Scenario bounds reflect uncertain receivable and inventory cycles.",
        annual_evidence(),
        "descending",
    ),
    assumption(
        "terminal_next_year_nopat",
        "cny",
        "3969800000",
        "5868400000",
        "7076600000",
        "Terminal-year EBIT after the effective tax proxy",
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
        "0.08",
        "0.10",
        "Bounded terminal incremental returns across mature auto-supplier economics",
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
for scenario_name, values in (
    ("bear", SCENARIOS["bear"]),
    ("base", SCENARIOS["base"]),
    ("bull", SCENARIOS["bull"]),
):
    BINDINGS.append(
        scenario_binding("wacc", scenario_name, "forecast.0.wacc", WACC)
    )
    BINDINGS.append(
        scenario_binding(
            "cash_tax_rate",
            scenario_name,
            "forecast.0.cash_tax_rate",
            CASH_TAX_RATE,
        )
    )
    BINDINGS.append(
        scenario_binding(
            "depreciation",
            scenario_name,
            "forecast.0.depreciation",
            DEPRECIATION,
        )
    )
    first = values["forecast"][0]
    last = values["forecast"][-1]
    BINDINGS.append(
        scenario_binding(
            "forecast_ebit_2026",
            scenario_name,
            "forecast.0.ebit",
            str(first["ebit"]),
        )
    )
    BINDINGS.append(
        scenario_binding(
            "forecast_ebit_2030",
            scenario_name,
            "forecast.4.ebit",
            str(last["ebit"]),
        )
    )
    BINDINGS.append(
        scenario_binding(
            "forecast_capex_2026",
            scenario_name,
            "forecast.0.capex",
            str(first["capex"]),
        )
    )
    BINDINGS.append(
        scenario_binding(
            "forecast_capex_2030",
            scenario_name,
            "forecast.4.capex",
            str(last["capex"]),
        )
    )
    BINDINGS.append(
        scenario_binding(
            "working_capital_increase_2026",
            scenario_name,
            "forecast.0.working_capital_increase",
            str(first["working_capital_increase"]),
        )
    )
    BINDINGS.append(
        scenario_binding(
            "working_capital_increase_2030",
            scenario_name,
            "forecast.4.working_capital_increase",
            str(last["working_capital_increase"]),
        )
    )
    terminal = values["terminal"]
    BINDINGS.append(
        scenario_binding(
            "terminal_next_year_nopat",
            scenario_name,
            "terminal.next_year_nopat",
            str(terminal["next_year_nopat"]),
        )
    )
    BINDINGS.append(
        scenario_binding(
            "terminal_growth",
            scenario_name,
            "terminal.growth",
            "0.02",
        )
    )
    BINDINGS.append(
        scenario_binding(
            "terminal_roic",
            scenario_name,
            "terminal.roic",
            str(terminal["roic"]),
        )
    )


def payload() -> dict[str, object]:
    return {
        "schema_version": "m1-valuation-package-v1",
        "package_version": "20260923.2",
        "descriptor_version": "600741-m1-valuation-v1",
        "symbol": SYMBOL,
        "name": NAME,
        "profile_id": "mature_manufacturing",
        "requested_model": "fcff",
        "run_id": "600741-m1-valuation-20260923",
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
                "published_at": "2026-03-30T16:00:00+00:00",
                "retrieved_at": "2026-09-23T00:54:00+00:00",
                "parser_version": "pdfium-m1-20260923",
            },
            {
                "id": INTERIM_ID,
                "kind": "official_issuer_filing",
                "location": INTERIM_PATH,
                "sha256": INTERIM_SHA256,
                "published_at": "2026-08-27T16:00:00+00:00",
                "retrieved_at": "2026-09-23T00:54:00+00:00",
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
            {
                "id": QUOTE_ID,
                "kind": "quote_session",
                "location": QUOTE_BUNDLE_PATH,
                "sha256": QUOTE_BUNDLE_SHA256,
                "retrieved_at": "2026-09-23T00:56:34+00:00",
                "parser_version": "quote-session-collection-v1",
            },
        ],
        "research_case": {
            "symbol": SYMBOL,
            "name": NAME,
            "as_of": "2026-09-22",
            "run_id": "600741-m1-valuation-20260923",
            "generated_at": "2026-09-23T08:00:00+08:00",
            "research_version": "600741-m1-valuation-v1",
            "industry": "汽车零部件",
            "investment_path": "成熟制造 / 客户周期受限的现金回报",
            "thesis": "智能座舱、底盘和动力总成平台已形成主要 OEM 配套规模，但客户集中、整车降价与行业下行要求把利润和再投资回报放在低置信度区间内检验。",
            "return_driver": "外部客户项目与新能源配套放量、平台化产品切换和经营现金转换；同时受整车客户周期和供应商价格竞争制约。",
            "mispricing_hypothesis": "未证明市场系统性低估。当前只检验低置信度 FCFF 区间能否容纳市价，不把当前价当作买入信号。",
            "financial_summary": {
                "period_end": "2026-06-30",
                "revenue_2025_cny": "183998900513.66",
                "parent_profit_2025_cny": "7207268139.61",
                "parent_equity_2025_cny": "67144573278.18",
                "weighted_roe_2025": "0.1073",
                "h1_2026_parent_profit_yoy": "-0.0867",
            },
            "positives": [
                {
                    "kind": "fact",
                    "text": "FY2025 审计报告签字确认，合并营业收入 1,839.99 亿元、归母净利润 72.07 亿元、归母净资产 671.45 亿元。",
                    "evidence_refs": [ANNUAL_ID],
                },
                {
                    "kind": "fact",
                    "text": "2026H1 主营业务收入汇总口径中，上汽集团以外整车客户占比 67.2%，智能底盘、座舱、动力总成等平台在多家外部客户量产或定点。",
                    "evidence_refs": [INTERIM_ID],
                },
                {
                    "kind": "fact",
                    "text": "FY2025 经营活动现金流净额 95.23 亿元，显著高于归母净利润，现金回款能力可观察。",
                    "evidence_refs": [ANNUAL_ID],
                },
            ],
            "counter_evidence": [
                {
                    "kind": "fact",
                    "text": "2026H1 营业收入同比 -1.43%、归母净利润 -8.67%、扣非归母净利润 -14.29%，利润降幅大于收入降幅。",
                    "evidence_refs": [INTERIM_ID],
                },
                {
                    "kind": "fact",
                    "text": "2026H1 国内汽车产量/销量同比 -4.0%/-4.1%；整车价格竞争向供应商的传导未被量化。",
                    "evidence_refs": [INTERIM_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "平台配套规模不能抵消客户周期和利润率压力；高现金流不等于可持续高资本回报。",
                    "evidence_refs": [ANNUAL_ID, INTERIM_ID],
                },
            ],
            "thesis_breakers": [
                {
                    "kind": "hypothesis",
                    "text": "若国内汽车产销继续下降或主要客户项目出现重大调整，平台化增长论点需要下调。",
                    "evidence_refs": [INTERIM_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若分产品毛利率、扣非利润和价格传导持续恶化，客户议价与成本控制假设受损。",
                    "evidence_refs": [INTERIM_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若应收、存货和营运资本持续扩大，或经营现金流改善来自不可持续回款时间差，现金转换质量需要撤回。",
                    "evidence_refs": [ANNUAL_ID, INTERIM_ID],
                },
            ],
            "next_events": [
                {
                    "kind": "fact",
                    "text": "观察下一份法定财务报告中的收入、分客户/分产品毛利率、经营现金流、应收、存货和资本开支。",
                    "evidence_refs": [INTERIM_ID],
                },
                {
                    "kind": "gap",
                    "text": "补充独立的客户结构、价格传导、ROIC/增量 ROIC 和完整再投资回报证据后再做正式人工批准。",
                    "evidence_refs": [INTERIM_ID],
                },
            ],
            "evidence_status": "verified",
            "valuation_status": "not_ready",
            "research_status": "financial_scope_approved",
            "blockers": [
                "formal G3 human valuation approval not present",
                "customer/cycle sensitivity and price transmission are not quantified",
                "ROIC and incremental ROIC remain unverified",
                "issuer-specific beta, credit spread and market-derived WACC remain unverified",
                "H1 2026 interim report is unaudited",
            ],
            "evidence_refs": [ANNUAL_REF, INTERIM_REF, COST_EQUITY_REF],
            "quote_date": "2026-09-22",
            "financial_period": "2026-06-30",
            "missing_date_reasons": {},
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
                "ebit": EBIT_2025,
                "cash_tax_rate": CASH_TAX_RATE,
                "depreciation": DEPRECIATION,
                "capex": CAPEX_2025,
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
        "quote": {
            "symbol": SYMBOL,
            "ref_id": QUOTE_ID,
            "bundle_path": QUOTE_BUNDLE_PATH,
            "bundle_sha256": QUOTE_BUNDLE_SHA256,
        },
        "model_validity_input": {
            "model_id": "fcff-shared-scenario-v1",
            "valid_from": "2026-09-22",
            "events": [],
            "event_scan_evidence_refs": [
                {
                    "id": INTERIM_ID,
                    "path": INTERIM_PATH,
                    "sha256": INTERIM_SHA256,
                    "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-28/1225516573.PDF",
                }
            ],
            "blockers": [],
        },
        "blockers": [
            "G3 human approval pending",
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
