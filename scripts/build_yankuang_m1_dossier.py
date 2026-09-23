"""Build the Yankuang Energy M1 provider dossier from its retained annual.

The provider only records facts read from the audited 2025 annual report and
marks cycle, normalized-earnings and model inputs that remain unresolved.
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


EVIDENCE_ID = "yankuang_2025_cninfo"
SOURCE_PDF = "runtime/candidate-financing-batch-20260909-02/600188-2b2585d4e6ea.pdf"
SOURCE_SHA256 = (
    "2b2585d4e6ea4677af4bbe89a720c6fca8909f695aeebc8d186d2ca2f70d82c6"
)


SPEC = {
    "symbol": "600188",
    "name": "兖矿能源",
    "as_of": "2026-09-23",
    "run_id": "yankuang-m1-dossier-v1",
    "research_version": "yankuang-m1-dossier-v1",
    "profile_id": "cyclical_cash_return",
    "primary_model": "cyclical_normalized",
    "financial_period": "2025-12-31",
    "valuation_status": "NOT_READY",
    "research_status": "financial_scope_partial",
    "evidence_refs": [
        {
            "id": EVIDENCE_ID,
            "kind": "official_issuer_filing",
            "source_id": "cninfo:1225048701",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-28/1225048701.PDF",
            "published_date": "2026-03-28",
            "period_end": "2025-12-31",
            "path": SOURCE_PDF,
            "sha256": SOURCE_SHA256,
            "description": "兖矿能源集团股份有限公司 2025 年年度报告（经审计，标准无保留意见）",
        }
    ],
    "sections": {
        "business_quality": {
            "status": SECTION_COMPLETE,
            "explanation": "资源、产品、产业链、行业结构、资本强度和现金转换已从报告建立可追溯覆盖；ROIC、资源经济价值与优势期仍显式 UNKNOWN。",
            "dimensions": [
                {
                    "key": BUSINESS_DIMENSION_MOAT,
                    "status": SECTION_COMPLETE,
                    "observation": "公司披露境内中国国家标准资源量 528.94 亿吨、境外 JORC 原地资源量 80.80 亿吨；覆盖动力煤、喷吹煤和焦煤，并拥有煤炭、化工和电力协同业务（p.17,30-31）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_PRICING_CUSTOMERS,
                    "status": SECTION_COMPLETE,
                    "observation": "最大客户销售额 127.41 亿元、占年度销售总额 9.6%；最大供应商山东能源采购额 77.04 亿元、占年度采购总额 17.2%，关联方集中度需要作为结构性事实处理（p.25）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_INDUSTRY_STRUCTURE,
                    "status": SECTION_COMPLETE,
                    "observation": "2025 年煤炭供需相对宽松，原煤产量增幅收窄，下游需求弱势；公司是主要煤炭生产商之一，兖煤澳洲是澳大利亚最大专营煤炭生产商（p.16）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_ROIC,
                    "status": SECTION_UNKNOWN,
                    "observation": "年报披露加权平均 ROE 9.95%，但没有提供可核验的 ROIC、增量 ROIC 或按资源/项目切分的资本回报。",
                },
                {
                    "key": BUSINESS_DIMENSION_REINVESTMENT,
                    "status": SECTION_COMPLETE,
                    "observation": "2025 年煤炭开发及开采相关资本性支出约 157.24 亿元；集团 2025 年资本性支出 220.52 亿元，2026 年计划 198.31 亿元；新增项目回报未有独立连续证据（p.32,38）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_CAPITAL_INTENSITY,
                    "status": SECTION_COMPLETE,
                    "observation": "2025 年末总资产 4529.44 亿元、负债总额 2818.47 亿元、归母净资产 1004.80 亿元；资本支出约为营业收入的 15.2%，属于高资本强度且高杠杆周期业务（p.9-10,38）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_CASH_CONVERSION,
                    "status": SECTION_COMPLETE,
                    "observation": "2025 年经营现金流净额 194.85 亿元；剔除山能财司金融活动影响后为 167.23 亿元，同比下降 39.3%，金融子/财务公司影响需要拆分后才能判断经营现金流质量（p.22）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_DURATION,
                    "status": SECTION_UNKNOWN,
                    "observation": "资源量和储量规模可观察，但正常化经济资源寿命、成本曲线位置和价格假设尚未独立核验，不能直接推断优势持续期。",
                },
            ],
            "findings": [
                {
                    "kind": "fact",
                    "text": "商品煤产量 1.824 亿吨、销量 1.712 亿吨；化工品产量 977.5 万吨、销量 857.4 万吨（p.16）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "公司拥有境内外多个矿区，重大煤矿建设项目合计设计产能 6,180 万吨/年，截至报告期末累计投资 250.13 亿元（p.32）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "资源和规模是可观察的事实优势，但商品价格由市场决定、客户/供应商存在关联方集中，不能把资源储备直接等同于稳定超额回报。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": [
                "正常化资源寿命与成本曲线未经独立核验",
            ],
        },
        "financial_quality": {
            "status": SECTION_COMPLETE,
            "explanation": "审计后收入、利润、现金流、业务毛利率和资产负债事实可追溯；正常化利润、维护资本开支和模型输入缺口继续显式保留。",
            "findings": [
                {
                    "kind": "fact",
                    "text": "2025 年营业收入 1449.33 亿元、同比 -7.49%；归母净利润 83.81 亿元、同比 -43.61%；扣非归母净利润 73.99 亿元、同比 -46.73%（p.9）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "加权平均 ROE 9.95%、同比下降 7.77 个百分点；基本 EPS 0.84 元；期末总股本 10,037,480,544 股（p.9-10）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "煤炭业务收入 886.66 亿元、毛利率 36.17%；自产煤收入 847.55 亿元、毛利率 37.35%；煤化工收入 242.93 亿元、毛利率 26.29%（p.22-23）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "经营现金流净额 194.85 亿元；剔除山能财司影响后 167.23 亿元、同比 -39.3%；投资活动现金流净额 -169.51 亿元（p.22）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "利润和现金回报明显回落，主要由煤炭价格和外部经营环境驱动；财务公司、同一控制下企业合并和汇兑因素使直接同比不充分，需要跨周期口径。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": [
                "正常化利润、维护资本开支和单位成本/运输口径未完成",
                "山能财司、少数股东和 H 股/A 股现金归属未拆分",
                "煤炭价格和成本没有完成独立外部对照",
            ],
        },
        "capital_allocation": {
            "status": SECTION_COMPLETE,
            "explanation": "分红政策、资本开支、股本变化和并购事实有原文；法人层级现金归属、项目回报和少数股东影响仍显式保留缺口。",
            "findings": [
                {
                    "kind": "fact",
                    "text": "根据 2023-2025 年度分红政策，2025 年度现金股利为 0.50 元/股（含税），扣除半年度 0.18 元/股后，董事会建议末期现金股利 0.32 元/股（p.2）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "2025 年因回购注销部分限制性股票，总股本由 10,039,860,402 股调整至 10,037,480,544 股（p.10）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "报告期合并西北矿业、兖矿能源（霍林郭勒）财务报表；2025 年收购西北矿业 51% 股权并完成追溯调整（p.10,37）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "高额资本开支、并购和分红并存；只有把每个项目的增量回报、少数股东比例和现金可分配层级核对清楚，才能判断资本配置是否创造价值。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": ["法人层级可分配现金、并购项目回报与少数股东现金归属未核验"],
        },
        "thesis": {
            "status": SECTION_COMPLETE,
            "explanation": "论点、回报驱动和误定价假设未建立均已完整表达；正常化估值与价格桥接仍为 NOT_READY。",
            "findings": [
                {
                    "kind": "interpretation",
                    "text": "研究论点：兖矿能源是否能依靠境内外的资源规模、煤化工/物流协同和国际化布局，在煤价下行周期中维持单位成本竞争力，并以纪律性资本开支和分红把周期现金转化为长期股东回报。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "回报驱动：煤炭价格、单位成本、资源寿命、澳洲资产、煤化工利润和资本开支/并购后的增量回报。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "gap",
                    "text": "误定价假设未建立：当前报告不能证明市场低估；利润和现金流的大幅周期波动也不能直接变成逆向买入理由。",
                    "status": SECTION_UNKNOWN,
                },
            ],
        },
        "counter_evidence": {
            "status": SECTION_COMPLETE,
            "findings": [
                {
                    "kind": "fact",
                    "text": "煤炭业务收入同比 -17.23%，自产煤毛利率下降 9.81 个百分点；贸易业务收入 82.50 亿元、同比 -50.66%（p.22-23,25）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "剔除财务公司影响后的经营现金流净额从上年同期 275.58 亿元降至 167.23 亿元，同比减少 39.3%；财务费用因汇兑损失增加 9.67 亿元（p.22）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "控股股东山东能源直接和间接持有公司 52.84% 股份；最大供应商为山东能源，前五大供应商采购额占比 34.0%（p.5,25）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "关联方集中、高杠杆和强周期现金流波动是当前最直接的负面证据，必须纳入正常化利润和治理评估。",
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
                    "text": "若煤价持续低于成本曲线且单位成本无法同步下降，正常化利润和资源价值需要大幅下修。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若资本开支和并购项目的回报持续低于资本成本，或少数股东/财务公司结构继续掩盖真实现金流，则多元化与并购论点受损。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若安全、环保或地缘政治事件造成停产、处罚或海外资产减值，正常化现金假设需要撤回。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若 2026 年实际资本支出明显超出计划，或分红政策在利润下滑后不可持续，现金回报叙事需要重估。",
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
                    "text": "观察 2026 年半年度报告中的煤价、产量、成本、经营现金流、资本开支和财务公司调整口径。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "跟踪 2025 年度末期分红方案的批准与实际派发，以及 2026 年分红政策。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "跟踪重大煤矿项目投产进度、资本开支执行、安全环保事件和澳煤价格/汇率的公开数据。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
        },
        "research_gaps": {
            "status": SECTION_COMPLETE,
            "explanation": "以下缺口保持可见，不把当前 PARTIAL 状态宣称为可估值或可交易。",
            "blockers": [
                "正常化利润、维护资本开支和单位成本/运输口径未完成",
                "山能财司、少数股东和 H 股/A 股现金归属未拆分",
                "煤炭价格和成本没有完成独立外部对照",
                "ROIC、增量 ROIC 与正常化资源寿命未经独立核验",
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
