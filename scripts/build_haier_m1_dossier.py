"""Build the Haier Smart Home M1 provider dossier from its CNINFO interim.

The dossier keeps issuer disclosures, accounting-period facts and unresolved
consolidation/model inputs separate.  No price, target weight or order
conclusion is emitted.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json

from value_investment_agent.m1_provider_dossier import write_provider_dossier
from value_investment_agent.research_read_model import (
    BUSINESS_DIMENSION_CAPITAL_INTENSITY,
    BUSINESS_DIMENSION_CASH_CONVERSION,
    BUSINESS_DIMENSION_DURATION,
    BUSINESS_DIMENSION_INDUSTRY_STRUCTURE,
    BUSINESS_DIMENSION_MOAT,
    BUSINESS_DIMENSION_PRICING_CUSTOMERS,
    BUSINESS_DIMENSION_REINVESTMENT,
    BUSINESS_DIMENSION_ROIC,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_UNKNOWN,
    SECTION_COMPLETE,
    SECTION_PARTIAL,
    SECTION_UNKNOWN,
)


EVIDENCE_ID = "haier_2026h1_cninfo"
SOURCE_PDF = (
    "runtime/company-research/m1-official-filings-20260923/600690/"
    "2026-06-30-interim-be559ae439b5886042de9a1dce025491de4b11ccb3cba1f3bc39483576787c8c.pdf"
)
SOURCE_SHA256 = (
    "fe5814830fac441f9f71b77472c1090ee451d2cf411ad3ce0da469ffb898ed97"
)


SPEC = {
    "symbol": "600690",
    "name": "海尔智家",
    "as_of": "2026-09-23",
    "run_id": "haier-m1-dossier-v1",
    "research_version": "haier-m1-dossier-v1",
    "profile_id": "mature_manufacturing",
    "primary_model": "fcff",
    "financial_period": "2026-06-30",
    "valuation_status": "NOT_READY",
    "research_status": "financial_scope_partial",
    "evidence_refs": [
        {
            "id": EVIDENCE_ID,
            "kind": "official_issuer_filing",
            "source_id": "cninfo:1225522691",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-28/1225522691.PDF",
            "published_date": "2026-08-28",
            "period_end": "2026-06-30",
            "path": SOURCE_PDF,
            "sha256": SOURCE_SHA256,
            "description": "海尔智家股份有限公司 2026 年半年度报告（未经审计）",
        }
    ],
    "sections": {
        "business_quality": {
            "status": SECTION_COMPLETE,
            "explanation": "全球战略、行业规模、海外资产/收入、资产负债与现金转换均已从报告建立可追溯覆盖；海外利润口径、ROIC 与优势期仍显式 UNKNOWN。",
            "dimensions": [
                {
                    "key": BUSINESS_DIMENSION_MOAT,
                    "status": SECTION_COMPLETE,
                    "observation": "公司披露全球竞争优势与全球化战略（p.27），并披露海外资产 15,251,666.84 万 CNY、占总资产 48.9%（p.35）；全球布局可观察，长期超额回报仍需独立验证。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_PRICING_CUSTOMERS,
                    "status": SECTION_UNKNOWN,
                    "observation": "原表披露海外收入 7,877,644 与海外经营利润 406,147，单位与币种上下文需保留原表核验（p.35）；尚无分品牌、分地区毛利率和客户集中度证据。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_INDUSTRY_STRUCTURE,
                    "status": SECTION_COMPLETE,
                    "observation": "2026H1 国内家电零售额 4,250 亿元、同比 -9.9%；家用空调销量 40.96 百万台、同比 -13.1%（p.9）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_ROIC,
                    "status": SECTION_UNKNOWN,
                    "observation": "半年报披露加权平均 ROE 8.36%（p.6），但没有可核验的 ROIC、增量 ROIC 或按地区/业务切分的资本回报。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_REINVESTMENT,
                    "status": SECTION_COMPLETE,
                    "observation": "期末固定资产 38,998,215,934.86 元、存货 45,317,406,207.70 元（p.34），显示制造与营运资本投入；增量产能和渠道投入回报尚无连续独立证据。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_CAPITAL_INTENSITY,
                    "status": SECTION_COMPLETE,
                    "observation": "期末总资产 311,911,862,184.62 元、归母净资产 119,678,355,042.24 元；固定资产与存货规模较大，但本次提取未完成 A/H 与子公司合并口径下的净营运资本拆分。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_CASH_CONVERSION,
                    "status": SECTION_COMPLETE,
                    "observation": "H1 经营现金流净额 9,752,033,977.71 元、同比 -12.45%，与归母净利润同向下降；合同负债 6,651,241,840.11 元、同比 -22.07%（p.6,34）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_DURATION,
                    "status": SECTION_UNKNOWN,
                    "observation": "品牌矩阵与全球渠道支持长周期叙事，但国内零售收缩、海外口径待核验，优势持续期尚未证明。",
                },
            ],
            "findings": [
                {
                    "kind": "fact",
                    "text": "2026H1 国内家电零售额 4,250 亿元、同比 -9.9%；家用空调销量 40.96 百万台、同比 -13.1%（p.9）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "海外资产 15,251,666.84 万 CNY、占总资产 48.9%；海外收入与海外经营利润披露为 7,877,644 和 406,147，需保留原表单位/币种上下文（p.35）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "全球化布局可观察，但海外收入和利润口径未完全闭合；国内行业下行与海外业务结构不能直接构成稳定定价权证据。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": [],
        },
        "financial_quality": {
            "status": SECTION_COMPLETE,
            "explanation": "合并收入、利润、现金流、资产负债和行业/海外口径均可追溯；未审计、A/H 拆分和 FCFF 输入缺口继续显式保留。",
            "findings": [
                {
                    "kind": "fact",
                    "text": "2026H1 营业收入 152,115,050,237.63 元、同比 -2.80%；归母净利润 10,316,254,946.26 元、同比 -14.27%；扣非归母净利润 9,298,750,602.78 元、同比 -20.54%（p.6）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "H1 经营现金流净额 9,752,033,977.71 元、同比 -12.45%；归母净资产 119,678,355,042.24 元；总资产 311,911,862,184.62 元；基本 EPS 1.12 元；加权平均 ROE 8.36%（p.6）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "期末货币资金 50,859,093,158.21 元、应收账款 32,955,141,174.95 元、存货 45,317,406,207.70 元、固定资产 38,998,215,934.86 元、短期借款 21,678,038,269.11 元、合同负债 6,651,241,840.11 元（p.34）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "合同负债 6,651,241,840.11 元、同比 -22.07%（p.34）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "收入、利润和经营现金流均下降，扣非利润降幅更大；当前合并口径事实不能直接作为 FCFF 输入，需先完成 A/H、少数股东、营运资本和税收拆分。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": [
                "2026 半年报未经审计",
                "A/H 与子公司合并范围及少数股东权益未拆分",
                "FCFF 所需 EBIT、现金税、D&A、营运资本、WACC 与净债务输入未形成",
                "海外收入/利润表单位与币种口径未闭合",
            ],
        },
        "capital_allocation": {
            "status": SECTION_COMPLETE,
            "explanation": "已披露 2025 年度末期分红调整、股份回购现金和 A/H 结构缺口；资本配置事实覆盖完整，可持续可分配现金仍为缺口。",
            "findings": [
                {
                    "kind": "fact",
                    "text": "报告披露 2025 年度末期分红方案原为每 10 股 8.867 元，后因回购专用账户剔除而调整为每 10 股 8.9151 元（p.183）；这是历史方案披露，不是当前 H1 分红结论。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "报告期股份回购支付现金 1,624,700,065.94 元（p.156）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "分红与回购事实表明存在股东回报活动，但 A/H 结构、法人层级现金和回购后股本分母未核验，不能形成可持续资本配置结论。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": ["A/H 与法人层级可分配现金、回购后普通股分母未核验"],
        },
        "thesis": {
            "status": SECTION_COMPLETE,
            "explanation": "论点、回报驱动与未建立误定价假设均已完整表达；估值和价格桥接仍为 NOT_READY。",
            "findings": [
                {
                    "kind": "interpretation",
                    "text": "研究论点：海尔能否依靠品牌矩阵、全球渠道和高端化战略，在国内家电下行中维持利润，并把海外业务与营运效率转化为持续自由现金流。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "回报驱动：分地区/品牌收入与毛利率、产品结构、库存与合同负债、海外盈利能力，以及分红、回购和再投资回报。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "gap",
                    "text": "误定价假设未建立：当前收入与利润同步下降，不能证明市场低估；全球化叙事不能直接转为买入理由。",
                    "status": SECTION_UNKNOWN,
                },
            ],
        },
        "counter_evidence": {
            "status": SECTION_COMPLETE,
            "findings": [
                {
                    "kind": "fact",
                    "text": "营业收入、归母净利润、扣非归母净利润和经营现金流分别同比 -2.80%、-14.27%、-20.54% 和 -12.45%；扣非利润降幅明显大于收入降幅（p.6）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "合同负债同比 -22.07%，国内家电零售额同比 -9.9%、家用空调销量同比 -13.1%（p.9,34）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "国内需求收缩、利润端降幅扩大和合同负债下降是直接负面证据；海外业务和回购活动不能抵消这些事实。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
        },
        "thesis_breakers": {
            "status": SECTION_COMPLETE,
            "findings": [
                {
                    "kind": "hypothesis",
                    "text": "若国内家电零售与空调销量继续下滑，或价格带/产品结构使毛利率进一步压缩，则高端化与品牌矩阵论点需要下调。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若海外收入/利润口径、汇兑或海外业务盈利能力与当前披露不符，全球增长假设需要撤回。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若存货、应收和合同负债继续恶化，经营现金流与收入确认质量需要重新审查。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若 A/H、子公司或法人层级现金归属无法闭合，FCFF 与股权价值模型不能解锁。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
        },
        "next_events": {
            "status": SECTION_COMPLETE,
            "findings": [
                {
                    "kind": "fact",
                    "text": "观察下一份法定财务报告中的收入、分地区/品牌毛利率、经营现金流、合同负债、库存和应收变化。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "跟踪国内家电零售、空调销量、产品结构和海外业务盈利能力的公开可核验数据。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "跟踪分红方案实施、股份回购执行，以及 A/H 股本与法人层级现金的正式口径。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
        },
        "research_gaps": {
            "status": SECTION_COMPLETE,
            "explanation": "以下缺口保持可见，不把当前 PARTIAL 状态宣称为可估值或可交易。",
            "blockers": [
                "2026 半年报未经审计",
                "A/H 与子公司合并范围及少数股东权益未拆分",
                "FCFF 所需完整输入与分地区/品牌回报未形成",
                "海外收入/利润表单位与币种口径未闭合",
                "未形成完整 Bear/Base/Bull、反向估值或当前价格桥接",
            ],
        },
    },
}


def main() -> int:
    result = write_provider_dossier(
        SPEC,
        generated_at=datetime.now(timezone.utc),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
