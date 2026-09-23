"""Build the Wuliangye M1 provider dossier from its retained CNINFO interim.

This is a provider-owned evidence extraction, not a company pipeline.  The
common builder in ``m1_provider_dossier`` keeps the dossier schema, reference
checks and hash-pinned runtime output identical across providers.
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
    SECTION_BLOCKED,
    SECTION_COMPLETE,
    SECTION_PARTIAL,
    SECTION_UNKNOWN,
)


EVIDENCE_ID = "wuliangye_2026h1_cninfo"
SOURCE_PDF = (
    "runtime/company-research/000858-peer-interim-20260909T125304973619Z/"
    "000858-1225531252.pdf"
)
SOURCE_SHA256 = (
    "15153679faee48d1b1b00c50557a88bdcbdf8cb4cbc49b8762e10f70210dfb5b"
)


SPEC = {
    "symbol": "000858",
    "name": "五粮液",
    "as_of": "2026-09-23",
    "run_id": "wuliangye-m1-dossier-v1",
    "research_version": "wuliangye-m1-dossier-v1",
    "profile_id": "quality_compounder",
    "primary_model": "residual_income_or_equity_value",
    "financial_period": "2026-06-30",
    "valuation_status": "NOT_READY",
    "research_status": "financial_scope_partial",
    "evidence_refs": [
        {
            "id": EVIDENCE_ID,
            "kind": "official_issuer_filing",
            "source_id": "cninfo:1225531252",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-29/1225531252.PDF",
            "published_date": "2026-08-29",
            "period_end": "2026-06-30",
            "path": SOURCE_PDF,
            "sha256": SOURCE_SHA256,
            "description": "宜宾五粮液股份有限公司 2026 年半年度报告全文（未经审计）",
        }
    ],
    "sections": {
        "business_quality": {
            "status": SECTION_COMPLETE,
            "explanation": "品牌、产区、产品量价、渠道、资本强度和现金转换已从报告建立可追溯覆盖；ROIC、增量 ROIC 与优势期仍显式 UNKNOWN。",
            "dimensions": [
                {
                    "key": BUSINESS_DIMENSION_MOAT,
                    "status": SECTION_COMPLETE,
                    "observation": "年报原文列示产区、元明古窖池群、五粮配方与技艺、品牌和浓香消费群体五类不可复制优势，并称古窖历史追溯至 1276 年（p.11）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_PRICING_CUSTOMERS,
                    "status": SECTION_COMPLETE,
                    "observation": "2026H1 酒类毛利率 84.61%；五粮液产品毛利率 87.91%，其他酒产品 60.47%；前五大经销商收入占销售收入 35.87%（p.9）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_INDUSTRY_STRUCTURE,
                    "status": SECTION_COMPLETE,
                    "observation": "公司明确行业仍面临外部环境不确定、有效需求恢复不及预期和白酒行业持续深度调整；未形成可核验的市场份额和周期位置量化表（p.15）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_ROIC,
                    "status": SECTION_UNKNOWN,
                    "observation": "半年报披露加权平均 ROE 7.14%，但没有可核验的 ROIC、增量 ROIC 或按业务与窖池资本切分的回报。",
                },
                {
                    "key": BUSINESS_DIMENSION_REINVESTMENT,
                    "status": SECTION_COMPLETE,
                    "observation": "研发投入 2.015 亿元；在建产能 4.4 万吨、设计年产能 21.0252 万吨，显示持续投入；新增产能和渠道投入的增量回报未有独立连续证据（p.10-11）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_CAPITAL_INTENSITY,
                    "status": SECTION_COMPLETE,
                    "observation": "期末固定资产 84.97 亿元、在建工程 65.48 亿元、存货 226.58 亿元，合计显著高于 H1 营业收入；固定资产占总资产 4.59%，但基酒与渠道营运资本占比高（p.13）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_CASH_CONVERSION,
                    "status": SECTION_COMPLETE,
                    "observation": "H1 经营现金流净额为 -21.54 亿元，同比由上年同期 +311.37 亿元转为负；期末合同负债 104.41 亿元，较上年末下降 30.18 亿元（p.7,13）。",
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "key": BUSINESS_DIMENSION_DURATION,
                    "status": SECTION_UNKNOWN,
                    "observation": "品牌、窖池和消费者基础支持长周期故事，但当前行业调整与收款政策变化尚未证明优势持续期和终端需求稳定性。",
                },
            ],
            "findings": [
                {
                    "kind": "fact",
                    "text": "2026H1 酒类收入 268.67 亿元，占总收入 94.55%；五粮液产品收入 236.32 亿元，其他酒产品收入 32.35 亿元（p.9,12）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "五粮液产品销量 16,292 吨、同比 +88.26%，生产量 17,781 吨、同比 -30.43%；其他酒产品销量 31,181 吨、同比 -63.75%（p.10）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "品牌和产区优势可观察，但销售费用大幅上升、合同负债下降和经营现金流转负表明需求验证仍需依赖后续动销与收款数据。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": [],
        },
        "financial_quality": {
            "status": SECTION_COMPLETE,
            "explanation": "收入、利润、现金流、费用和资产负债事实可追溯；未审计、会计差错基期和模型输入缺口继续显式保留。",
            "findings": [
                {
                    "kind": "fact",
                    "text": "2026H1 营业收入 284.17 亿元、同比 +20.87%；归母净利润 87.53 亿元、同比 +89.30%；扣非归母净利润 84.83 亿元、同比 +83.96%（p.6）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "H1 加权平均 ROE 7.14%、基本 EPS 2.2551 元；经营现金流净额 -21.54 亿元，同比 -106.92%（p.7,124）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "销售费用 63.22 亿元、同比 +80.65%；营业成本 55.995 亿元、同比 +7.61%；管理费用下降 12.21%（p.11）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "期末货币资金 1190.89 亿元；受限货币资金 2.698 亿元、其他流动资产受限 45.07 亿元；合同负债 104.41 亿元、存货 226.58 亿元（p.13-14）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "利润增幅主要由上年同期基数较低和春节旺季动销解释；高额销售投入、收款政策变化与负经营现金流使利润增长质量仍不能直接外推。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": [
                "2026 半年报未经审计",
                "会计差错更正后的基期可比口径需要完整复核",
                "质量 compounder 所需的 ROIC、增量 ROIC 与优势期输入未形成",
            ],
        },
        "capital_allocation": {
            "status": SECTION_COMPLETE,
            "explanation": "分红、回购、控股股东增持事实明确；法人层级净现金、可分配现金和回购后股本分母仍显式保留缺口。",
            "findings": [
                {
                    "kind": "fact",
                    "text": "公司 2025 年度利润分配已派发现金红利总额约 100 亿元；本期计划半年度不派发现金红利（p.16,18）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "回购方案金额不低于 80 亿元、不超过 100 亿元，全部用于注销；截至 2026-07-31 已回购 13,316,606 股，占总股本 0.34%，金额 10.018 亿元（p.16）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "五粮液集团于 2026-05-07 启动第三轮增持；截至 2026-08-07 增持 2,411,300 股，占总股本 0.06%，金额 1.994 亿元，计划尚未实施完毕（p.16-17）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "回购注销和控股股东增持是有形的股东回报行动，但 H1 经营现金流为负、受限资产和渠道政策变化意味着不能把账面现金直接视为可持续可分配现金。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
            ],
            "blockers": ["法人层级可分配现金与回购注销后的普通股分母未核验"],
        },
        "thesis": {
            "status": SECTION_COMPLETE,
            "explanation": "论点、回报驱动和误定价假设未建立均已完整表达；估值与价格桥接仍为 NOT_READY。",
            "findings": [
                {
                    "kind": "interpretation",
                    "text": "研究论点：五粮液是否能依靠产区、古窖、品质、品牌和浓香消费群体，在行业深度调整中维持核心产品的价格与渠道质量，并把新增产能和股东回报转化为持续资本回报。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "回报驱动：核心五粮液产品量价与毛利率、渠道预收与动销质量、产能和品牌投入回报，以及分红、回购和控股股东增持。",
                    "confidence": CONFIDENCE_LOW,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "gap",
                    "text": "误定价假设未建立：当前报告只能观察经营事实，不能证明市场低估；负经营现金流和销售投入增加不能直接转为买入理由。",
                    "status": SECTION_UNKNOWN,
                },
            ],
        },
        "counter_evidence": {
            "status": SECTION_COMPLETE,
            "findings": [
                {
                    "kind": "fact",
                    "text": "H1 经营现金流净额为 -21.54 亿元，而收入同比增长 20.87%；合同负债较上年末减少 30.18 亿元，显示收款政策和渠道节奏发生明显变化（p.7,13）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "销售费用同比增长 80.65%，主要由市场投入增加；其他酒产品销量下降 63.75%，公司称低价位酒存量竞争加剧（p.10-11）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "前五大经销商收入占销售收入 35.87%，主要采取先款后货；客户和渠道集中度会放大渠道去库存或动销变化的影响（p.9）。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "interpretation",
                    "text": "这些事实不能证明品牌或公司不可投资，但足以阻止把当前高利润增速直接解读为需求全面恢复。",
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
                    "text": "若下一期经营现金流和合同负债继续下降，或销售费用率维持高位而收入未能匹配，则“动销改善与渠道质量”论点需要下调。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若核心五粮液产品出现价盘松动、毛利率或高端产品收入占比明显下降，则品牌溢价与定价权假设受损。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若回购注销、控股股东增持或年度分红明显低于披露方案，则资本配置信号需要重新评估。",
                    "confidence": CONFIDENCE_UNKNOWN,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "hypothesis",
                    "text": "若会计差错更正后的重述口径与本期报告口径出现未解释差异，则历史利润和增长假设需要撤回。",
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
                    "text": "观察下一份法定财务报告中的收入、毛利率、销售费用、经营现金流、合同负债和库存变化。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "跟踪回购注销、控股股东增持的完成情况，以及年度分红方案。",
                    "confidence": CONFIDENCE_MEDIUM,
                    "evidence_refs": [EVIDENCE_ID],
                },
                {
                    "kind": "fact",
                    "text": "跟踪批价、经销商库存、开瓶动销和终端价格的公开可核验数据，作为公司管理层口径的独立校验。",
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
                "会计差错更正后的基期可比口径需要完整复核",
                "ROIC、增量 ROIC 与优势期未计算或未验证",
                "法人层级可分配现金与回购注销后的普通股分母未核验",
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
