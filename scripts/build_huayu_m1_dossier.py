"""Build the Huayu Automotive Systems M1 provider dossier from its CNINFO interim.

The dossier records the filing facts and keeps customer/cycle sensitivity and
FCFF model inputs visibly unresolved.  It remains ``action=no_order``.
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


EVIDENCE_ID = "huayu_2026h1_cninfo"
SOURCE_PDF = (
    "runtime/company-research/m1-official-filings-20260923/600741/"
    "2026-06-30-interim-2b5ced0dc37827ad9d35036fb0d49b3b34e6ff47f2559222db0225f7519162c6.pdf"
)
SOURCE_SHA256 = (
    "77db47cdf18cc46123c4924cb869a75dc3d4404f718e132292e6c9132e65f2f9"
)


SPEC = {
    "symbol": "600741",
    "name": "华域汽车",
    "as_of": "2026-09-23",
    "run_id": "huayu-m1-dossier-v1",
    "research_version": "huayu-m1-dossier-v1",
    "profile_id": "mature_manufacturing",
    "primary_model": "fcff",
    "financial_period": "2026-06-30",
    "valuation_status": "NOT_READY",
    "research_status": "financial_scope_partial",
    "evidence_refs": [
        {
            "id": EVIDENCE_ID,
            "kind": "official_issuer_filing",
            "source_id": "cninfo:1225516573",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-28/1225516573.PDF",
            "published_date": "2026-08-28",
            "period_end": "2026-06-30",
            "path": SOURCE_PDF,
            "sha256": SOURCE_SHA256,
            "description": "华域汽车系统股份有限公司 2026 年半年度报告（未经审计）",
        }
    ],
    "sections": {
        "business_quality": {
            "status": SECTION_COMPLETE,
            "explanation": "平台化产品、主要 OEM 关系、行业产销和现金转换已建立可追溯覆盖；分客户毛利率、价格传导、ROIC 与优势期仍显式 UNKNOWN。",
            "dimensions": [
                {
                    "key": BUSINESS_DIMENSION_MOAT,
                    "status": SECTION_COMPLETE,
                    "observation": "公司披露智能座舱、底盘和动力总成等平台化产品及主要整车客户/项目，包括上汽相关和外部整车客户（p.9）；这是发行人陈述，需要独立验证产品切换壁垒和客户黏性。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_PRICING_CUSTOMERS,
                    "status": SECTION_UNKNOWN,
                    "observation": "报告披露主要整车客户与项目（p.9），但未形成分客户收入、毛利率和价格传导证据，不能判断议价能力。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_INDUSTRY_STRUCTURE,
                    "status": SECTION_COMPLETE,
                    "observation": "2026H1 中国汽车产量/销量分别为 1,499.3 万辆和 1,501.7 万辆、同比 -4.0%/-4.1%；新能源汽车产销分别为 743.8 万辆和 744.6 万辆、同比 +6.7%/+7.3%，占汽车销量 49.6%（p.8）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_ROIC,
                    "status": SECTION_UNKNOWN,
                    "observation": "半年报披露加权平均 ROE 3.87%（p.6），但没有可核验的 ROIC、增量 ROIC 或按业务/客户切分的资本回报。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_REINVESTMENT,
                    "status": SECTION_UNKNOWN,
                    "observation": "本次提取事实未包含可核验的资本开支、研发投入和新增项目回报拆分，无法判断再投资效率。",
                },
                {
                    "key": BUSINESS_DIMENSION_CAPITAL_INTENSITY,
                    "status": SECTION_COMPLETE,
                    "observation": "期末总资产 197,377,630,675.08 元、归母净资产 66,539,209,370.11 元（p.6）；但固定资产、营运资本和客户项目资本占用未完成拆分，不能确定 FCFF 资本强度。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_CASH_CONVERSION,
                    "status": SECTION_COMPLETE,
                    "observation": "H1 经营现金流净额 7,968,284,037.38 元、同比 +16.69%，而收入和利润下降，现金转换质量需要结合应收、存货和客户回款连续数据验证（p.6）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_DURATION,
                    "status": SECTION_UNKNOWN,
                    "observation": "平台化产品与主要 OEM 关系可能形成切换成本，但智能电动化转型中的技术迭代和客户结构使优势持续期尚未验证。",
                },
            ],
            "findings": [
                {
                    "kind": "fact",
                    "text": "2026H1 中国汽车产量/销量 1,499.3 万辆/1,501.7 万辆、同比 -4.0%/-4.1%；新能源汽车产销 743.8 万辆/744.6 万辆、同比 +6.7%/+7.3%，占汽车销量 49.6%（p.8）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "公司披露智能座舱、底盘、动力总成平台及主要整车客户/项目，包括上汽相关与外部整车客户（p.9）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "平台化和新能源汽车配套可观察，但客户集中、整车价格竞争和技术迭代可能压缩供应商利润率；该观察不能直接证明稳定护城河。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": [],
        },
        "financial_quality": {
            "status": SECTION_COMPLETE,
            "explanation": "合并收入、利润、现金流、资产负债和行业产销均可追溯；未审计、客户周期与 FCFF 输入缺口继续显式保留。",
            "findings": [
                {
                    "kind": "fact",
                    "text": "2026H1 营业收入 83,938,596,743.94 元、同比 -1.43%；归母净利润 2,646,591,006.98 元、同比 -8.67%；扣非归母净利润 2,309,762,348.23 元、同比 -14.29%（p.6）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "H1 经营现金流净额 7,968,284,037.38 元、同比 +16.69%；归母净资产 66,539,209,370.11 元；总资产 197,377,630,675.08 元；基本 EPS 0.839 元；加权平均 ROE 3.87%（p.6）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "公司 H1 收入降幅小于同期国内汽车产销降幅（p.6,8）；该对照不能替代按客户、产品和价格拆分的收入质量验证。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "收入相对稳健但利润端降幅更大，经营现金流增长可能来自营运资本时间性变化；这些合并事实不能直接作为 FCFF 输入。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": [
                "2026 半年报未经审计",
                "客户/周期敏感性与价格传导未量化",
                "FCFF 所需 EBIT、现金税、D&A、净营运资本、资本开支、WACC 与净债务输入未形成",
                "经营现金流增长的营运资本与客户回款原因未核验",
            ],
        },
        "capital_allocation": {
            "status": SECTION_COMPLETE,
            "explanation": "本期不分配已形成原文证据；分红政策、资本开支与可持续现金回报的长期证据仍显式保留缺口。",
            "findings": [
                {
                    "kind": "fact",
                    "text": "报告披露 2026 年半年度不进行利润分配，也不进行资本公积转增股本（p.20）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "本期不分配本身不是结论；需要结合年度资本开支、客户应收和现金需求判断长期资本配置质量，当前证据不足。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": ["分红政策、资本开支与可分配现金的连续证据未核验"],
        },
        "thesis": {
            "status": SECTION_COMPLETE,
            "explanation": "论点、回报驱动与未建立误定价假设均已完整表达；估值和价格桥接仍为 NOT_READY。",
            "findings": [
                {
                    "kind": "interpretation",
                    "text": "研究论点：华域能否依靠平台化零部件、主要 OEM 关系和新能源汽车配套，在整车价格竞争与客户结构变化中维持利润和自由现金流。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "回报驱动：分客户/产品收入与毛利率、平台化订单转化、新能源汽车配套、营运资本与价格传导，以及资本配置。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "gap",
                    "text": "误定价假设未建立：收入相对行业稍稳不能证明市场低估，客户周期和利润率压力使当前事实不能直接转为买入理由。",
                    "status": SECTION_UNKNOWN,
                },
            ],
        },
        "counter_evidence": {
            "status": SECTION_COMPLETE,
            "findings": [
                {
                    "kind": "fact",
                    "text": "归母净利润同比 -8.67%、扣非归母净利润同比 -14.29%，利润降幅明显大于收入降幅；加权平均 ROE 3.87%（p.6）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "国内汽车产销分别同比 -4.0%/-4.1%，行业下行；新能源汽车高增长与供应商利润实现之间没有直接证据（p.8）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "客户周期、整车价格竞争和利润率下降是直接风险；经营现金流增长不能抵消这些负面证据。",
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
                    "text": "若国内汽车产销继续下降，或主要客户销量与项目配套出现重大调整，则平台化增长论点需要下调。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若整车价格竞争向供应商持续传导，分产品毛利率和扣非利润继续恶化，则客户议价与成本控制假设受损。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若应收、存货和营运资本持续扩大，或经营现金流增长来自不可持续回款时间差，现金转换质量需要撤回。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若 FCFF 输入或客户周期调整无法形成，通用制造模型不能直接解锁华域的估值。",
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
                    "text": "观察下一份法定财务报告中的收入、分客户/产品毛利率、经营现金流、应收、存货和资本开支。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "跟踪国内汽车与新能源汽车产销、主要 OEM 项目平台切换和供应商价格传导的公开数据。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "跟踪年度分红方案、资本开支计划与客户应收/回款周期，形成完整资本配置证据。",
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
                "分客户、分产品收入与毛利率未核验",
                "客户/周期敏感性与价格传导未量化",
                "FCFF 与周期调整所需完整输入未形成",
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
