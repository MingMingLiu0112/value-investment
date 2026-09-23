"""Build the Yili M1 provider dossier from its retained CNINFO interim.

This script records only facts read from the pinned filing.  Issuer narrative,
accounting-period noise and unresolved franchise inputs stay visibly separated
from the valuation model; the dossier remains ``action=no_order``.
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


EVIDENCE_ID = "yili_2026h1_cninfo"
SOURCE_PDF = (
    "runtime/company-research/m1-official-filings-20260923/600887/"
    "2026-06-30-interim-6c456d8e5f19ba114b2cac48595f997612f66b337d294265975ed5eb7c3499ab.pdf"
)
SOURCE_SHA256 = (
    "423af4d63f2b620a03ed9d0080adbb063f3ef14d874abeca8097d0e0d1441ac2"
)


SPEC = {
    "symbol": "600887",
    "name": "伊利股份",
    "as_of": "2026-09-23",
    "run_id": "yili-m1-dossier-v1",
    "research_version": "yili-m1-dossier-v1",
    "profile_id": "quality_compounder",
    "primary_model": "residual_income_or_equity_value",
    "financial_period": "2026-06-30",
    "valuation_status": "NOT_READY",
    "research_status": "financial_scope_partial",
    "evidence_refs": [
        {
            "id": EVIDENCE_ID,
            "kind": "official_issuer_filing",
            "source_id": "cninfo:1225511409",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-27/1225511409.PDF",
            "published_date": "2026-08-27",
            "period_end": "2026-06-30",
            "path": SOURCE_PDF,
            "sha256": SOURCE_SHA256,
            "description": "内蒙古伊利实业集团股份有限公司 2026 年半年度报告（未经审计）",
        }
    ],
    "sections": {
        "business_quality": {
            "status": SECTION_COMPLETE,
            "explanation": "品牌、市场份额、分产品收入/成本、渠道、供应链与现金转换已从报告建立可追溯覆盖；ROIC/增量 ROIC 与优势持续期仍显式保持 UNKNOWN。",
            "dimensions": [
                {
                    "key": BUSINESS_DIMENSION_MOAT,
                    "status": SECTION_COMPLETE,
                    "observation": "报告披露凯度 BrandZ 全球乳业第一、Brand Finance 中国品牌价值 500 强乳业第一、全球 77 个生产基地、1,600 余万吨/年产能，以及渠道、品质和创新体系（p.12-14）；品牌与产能事实可观察，仍需独立长期经营证据验证持续期。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_PRICING_CUSTOMERS,
                    "status": SECTION_COMPLETE,
                    "observation": "分部主营收入与成本显示液体乳、奶粉及奶制品、冷饮毛利率分别约 34.15%、41.37%、39.06%，其他分部约 5.30%（p.199）；分产品高毛利结构可观察，但价格带和客户集中度仍待补充。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_INDUSTRY_STRUCTURE,
                    "status": SECTION_COMPLETE,
                    "observation": "报告引用尼尔森与星图第三方数据：婴幼儿奶粉零售额份额 18.6%、同比 +0.6pct，成人奶粉份额 26.8%，均居行业第一（p.8-9）；公司渠道覆盖和全球供应链披露在 p.12-13。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_ROIC,
                    "status": SECTION_UNKNOWN,
                    "observation": "半年报披露加权平均 ROE 10.09%（p.3），但没有可核验的 ROIC、增量 ROIC 或按业务切分的资本回报。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_REINVESTMENT,
                    "status": SECTION_COMPLETE,
                    "observation": "H1 研发费用 397,446,008.40 元、购建长期资产支付现金 1,304,262,044.68 元，投资活动现金流净额 -13,195,068,088.81 元（p.14,53）；投入规模可观察，增量回报仍需后续验证。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_CAPITAL_INTENSITY,
                    "status": SECTION_COMPLETE,
                    "observation": "期末总资产 157,165,308,525.12 元、归母净资产 53,711,364,981.99 元；应收、商誉、大额存单/定期存款等营运与金融资产占比高，境外资产 206.46 亿元、占总资产 13.14%（p.3,16-17,19）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_CASH_CONVERSION,
                    "status": SECTION_COMPLETE,
                    "observation": "H1 经营现金流净额 9,759,147,483.18 元、同比 +229.23%，显著高于归母净利润；公司解释为回款与时间性因素（p.3,14）。合同负债下降和短期借款上升需要作为现金质量对照。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_DURATION,
                    "status": SECTION_UNKNOWN,
                    "observation": "品牌与全国冷链渠道支持长周期故事，但当前利润下降、渠道收款变化和减值尚未证明优势持续期。",
                },
            ],
            "findings": [
                {
                    "kind": "fact",
                    "text": "2026H1 奶粉及奶制品业务收入 168.45 亿元，整体市场份额居行业第一；婴幼儿奶粉零售额份额 18.6%、成人奶粉零售额份额 26.8%（p.8-9）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "报告分部主营业务收入为液体乳 365.90 亿元、奶粉及奶制品 170.53 亿元、冷饮 90.73 亿元、其他 10.58 亿元；对应主营成本使分部毛利率可独立计算（p.199）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "公司披露新产品收入占比约 15.8%（p.3,12）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "公司将其竞争优势归为多元化产品组合、品牌、渠道、质量、创新和全球供应链（p.12-13）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "品牌与全国渠道叙事可观察，但属于发行人陈述；新产品占比不能直接证明品牌护城河、定价权或未来资本回报。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": [],
        },
        "financial_quality": {
            "status": SECTION_COMPLETE,
            "explanation": "合并利润、现金流、资产负债和分部收入/成本均可追溯到原报告；未审计、减值调整和模型输入缺口继续保留在 blockers。",
            "findings": [
                {
                    "kind": "fact",
                    "text": "2026H1 营业收入 64,330,936,547.38 元、同比 +4.13%；归母净利润 5,758,628,097.79 元、同比 -20.02%；扣非归母净利润 5,595,762,517.76 元、同比 -20.25%（p.3）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "H1 经营现金流净额 9,759,147,483.18 元、同比 +229.23%；归母净资产 53,711,364,981.99 元；总资产 157,165,308,525.12 元；基本 EPS 0.91 元；加权平均 ROE 10.09%（p.3）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "H1 投资活动现金流净额 -13,195,068,088.81 元，筹资活动现金流净额 -241,598,720.31 元；经营现金流改善被公司解释为回款与时间性因素（p.14）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "H1 营业成本 40,894,077,275.25 元、销售费用 11,432,167,134.28 元、管理费用 2,470,895,867.58 元、研发费用 397,446,008.40 元（p.14）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "H1 购建固定资产、无形资产和其他长期资产支付现金 1,304,262,044.68 元；分配股利、利润或偿付利息支付现金 6,287,065,552.99 元（p.53）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "期末合同负债 4,948,856,599.18 元、较期初下降 53.15%；短期借款 64,677,193,034.15 元、较期初上升 41.74%；应收账款 4,077,520,954.97 元（p.16）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "报告期商誉减值损失 1,546,544,866.49 元；资产减值损失合计 2,455,875,173.02 元，主要为澳优商誉及存货减值（p.164）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "收入增长而利润明显下降，经营现金流大幅增长主要由回款与时间性因素解释；减值、合同负债下降和短期借款上升意味着不能直接把利润或现金流单独外推。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": [
                "2026 半年报未经审计",
                "减值、非经常性项目与可续经营利润未完成调整",
            ],
        },
        "capital_allocation": {
            "status": SECTION_COMPLETE,
            "explanation": "本期分红方案、回购现金、股利/利息现金支出和股份回购均已有原文证据；普通股分母与可持续可分配现金仍显式保留缺口。",
            "findings": [
                {
                    "kind": "fact",
                    "text": "报告披露 2026 年半年度不进行利润分配，也不进行资本公积转增股本（p.1,27）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "报告期股份回购支付现金 251,737,303.29 元（p.169）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "H1 分配股利、利润或偿付利息支付现金 6,287,065,552.99 元（p.53）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "本期无分红、回购现金规模较小；在利润下滑和减值背景下，尚未形成可持续可分配现金或股东回报政策的独立结论。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": ["普通股分母、可分配现金与资本配置政策未核验"],
        },
        "thesis": {
            "status": SECTION_COMPLETE,
            "explanation": "论点、回报驱动和误定价假设未建立均已完整表达；估值与价格桥接不属于本档案，仍为 NOT_READY。",
            "findings": [
                {
                    "kind": "interpretation",
                    "text": "研究论点：伊利能否依靠全国品牌、渠道与冷链供应链，在乳制品消费和产品结构变化中维持利润率，并把多元化产品、全球化与再投资转化为持续资本回报。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "回报驱动：分产品量价与毛利率、渠道回款与库存质量、新产品收入贡献、减值后的可续利润，以及分红/回购与再投资回报。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "gap",
                    "text": "误定价假设未建立：当前事实只能观察经营变化，不能证明市场低估；利润下滑和现金流的时间性改善不能直接转为买入理由。",
                    "status": SECTION_UNKNOWN,
                },
            ],
        },
        "counter_evidence": {
            "status": SECTION_COMPLETE,
            "findings": [
                {
                    "kind": "fact",
                    "text": "收入 +4.13% 而归母净利润 -20.02%、扣非归母净利润 -20.25%；商誉减值 15.47 亿元、资产减值合计 24.56 亿元（p.3,164）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "合同负债较期初下降 53.15%，短期借款上升 41.74%；经营现金流 +229.23% 被公司解释为回款与时间性因素（p.14,16）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "这些事实不能证明品牌或公司不可投资，但足以阻止把现金流高增长直接解读为经营质量全面改善。",
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
                    "text": "若下一期经营现金流回落到利润水平、应收或借款继续上升、合同负债继续下降，则“回款改善与渠道质量”论点需要下调。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若澳优或相关品牌继续出现重大商誉/资产减值，或并购后的增量回报持续缺失，则多元化再投资论点受损。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若核心乳制品价格、毛利率或市场份额明显下降，品牌与全国渠道护城河假设需要撤回。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若普通股分母、可分配现金或持续分红/回购证据不支持权益价值输入，则 residual income/equity value 模型不能解锁。",
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
                    "text": "观察下一份法定财务报告中的收入、分产品毛利率、经营现金流、合同负债、应收、短期借款和库存变化。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "跟踪澳优及其他并购资产的后续经营、减值测试和新产品收入贡献。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "补充独立的市场份额、终端动销、价格带、渠道库存和利润率数据，作为公司披露口径的交叉验证。",
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
                "分产品价格带、毛利率、市场份额与客户集中度未独立验证",
                "ROIC、增量 ROIC 与竞争优势持续期未计算或未验证",
                "普通股分母、可分配现金与持续再投资回报未核验",
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
