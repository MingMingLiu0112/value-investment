"""Build the first real M1 provider dossier from Gree's pinned CNINFO filing.

The PDF remains the source of truth.  This script records only facts extracted
from that filing, separates issuer statements from our interpretations, keeps
unresolved model inputs visible, and never emits a price or order conclusion.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

from value_investment_agent.research_read_model import (
    ACTION_NO_ORDER,
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
    DOSSIER_SCHEMA_VERSION,
    ResearchDimension,
    ResearchDossier,
    SECTION_BLOCKED,
    SECTION_COMPLETE,
    SECTION_PARTIAL,
    SECTION_UNKNOWN,
    section,
    statement,
)


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "runtime/company-research/000651-official-interim-20260917/1225515004.pdf"
PDF_SHA256 = "50da2e03fddbe9dd424d8fe7881f47fb34efa5d38c96aa9449c12e445c3b2dec"
SOURCE_URL = "https://static.cninfo.com.cn/finalpage/2026-08-27/1225515004.PDF"
EVIDENCE_ID = "gree_2026h1_cninfo"


def _ref() -> dict[str, str]:
    if not PDF.is_file() or hashlib.sha256(PDF.read_bytes()).hexdigest() != PDF_SHA256:
        raise ValueError("Pinned Gree CNINFO filing is missing or changed")
    return {
        "id": EVIDENCE_ID,
        "kind": "official_issuer_filing",
        "source_id": "cninfo:1225515004",
        "source_url": SOURCE_URL,
        "published_date": "2026-08-27",
        "period_end": "2026-06-30",
        "path": str(PDF.relative_to(ROOT)),
        "sha256": PDF_SHA256,
        "description": "格力电器 2026 年半年度报告全文（未经审计）",
    }


def _business() -> tuple["ResearchSection", dict[str, str]]:
    dimensions = (
        ResearchDimension(
            BUSINESS_DIMENSION_MOAT,
            SECTION_COMPLETE,
            "品牌价值 2,103.51 亿元、累计专利与授权、标准制定及质量体系均可观察（p.20-21）。",
            evidence_refs=[EVIDENCE_ID],
        ),
        ResearchDimension(
            BUSINESS_DIMENSION_PRICING_CUSTOMERS,
            SECTION_COMPLETE,
            "消费电器毛利率 31.77%，内销主营毛利率 31.94%，外销主营毛利率 19.80%；海外收入同比 -21.98%（p.24）。",
            evidence_refs=[EVIDENCE_ID],
        ),
        ResearchDimension(
            BUSINESS_DIMENSION_INDUSTRY_STRUCTURE,
            SECTION_COMPLETE,
            "2026H1 国内家电零售额 4,250 亿元、同比 -9.9%；家用空调总销量 11,552.5 万台、同比 -6.2%；低端机型占比持续上升（p.10）。",
            evidence_refs=[EVIDENCE_ID],
        ),
        ResearchDimension(
            BUSINESS_DIMENSION_ROIC,
            SECTION_UNKNOWN,
            "半年报披露加权平均 ROE 8.68%，但未形成可核验 ROIC/增量 ROIC；财务公司、受限现金与融资结构尚未拆分，不能机械换算。",
        ),
        ResearchDimension(
            BUSINESS_DIMENSION_REINVESTMENT,
            SECTION_COMPLETE,
            "购建长期资产现金 7.30 亿元，研发投入 31.52 亿元；工业第二曲线的增量资本回报尚无连续、独立证据。",
            evidence_refs=[EVIDENCE_ID],
        ),
        ResearchDimension(
            BUSINESS_DIMENSION_CAPITAL_INTENSITY,
            SECTION_COMPLETE,
            "固定资产 337.30 亿元、占总资产 8.45%；购建长期资产现金约占 H1 营业收入 0.82%，账面资本强度偏低。",
            evidence_refs=[EVIDENCE_ID],
        ),
        ResearchDimension(
            BUSINESS_DIMENSION_CASH_CONVERSION,
            SECTION_COMPLETE,
            "H1 经营现金流 188.09 亿元，为归母净利润 132.78 亿元的约 1.42 倍；合同负债和库存同步下降。",
            evidence_refs=[EVIDENCE_ID],
        ),
        ResearchDimension(
            BUSINESS_DIMENSION_DURATION,
            SECTION_UNKNOWN,
            "品牌、渠道和核心技术可观察，但当前需求下行与价格带下移环境尚未证明竞争优势的持续时间。",
        ),
    )
    findings = (
        statement(
            "fact",
            "2026H1 消费电器收入 740.74 亿元、占 82.86%；工业制品及绿色能源 86.52 亿元、占 9.68%（p.24）。",
            confidence=CONFIDENCE_MEDIUM,
            evidence_refs=[EVIDENCE_ID],
        ),
        statement(
            "fact",
            "格力品牌空调线上市场占有率为 24.2%，行业排名第一；公司与京东有三年 1,000 万套 AI 产品合作（p.14）。",
            confidence=CONFIDENCE_MEDIUM,
            evidence_refs=[EVIDENCE_ID],
        ),
        statement(
            "interpretation",
            "品牌、研发、制造和渠道是可观察优势；但这些优势尚不足以证明需求下行期间的长期超额资本回报。",
            confidence=CONFIDENCE_LOW,
            evidence_refs=[EVIDENCE_ID],
        ),
        statement(
            "fact",
            "2026H1 内销主营收入 725.12 亿元、同比 +1.90%；外销主营收入 127.44 亿元、同比 -21.98%（p.24）。",
            confidence=CONFIDENCE_MEDIUM,
            evidence_refs=[EVIDENCE_ID],
        ),
        statement(
            "fact",
            "国内零售端 2,100 元以下空调机型销量占比升至 54.45%，同比提高 6.97 个百分点（p.10）。",
            confidence=CONFIDENCE_MEDIUM,
            evidence_refs=[EVIDENCE_ID],
        ),
    )
    blockers = (
        "ROIC 与增量 ROIC 未计算",
        "竞争优势持续期未经长期经营证据验证",
    )
    return (
        section(
            "business_quality",
            "Business Quality",
            SECTION_COMPLETE,
            findings=findings,
            dimensions=dimensions,
            blockers=blockers,
            explanation="品牌、产品结构、行业结构和现金转换已有官方披露；ROIC 与优势期保持显式 UNKNOWN。",
        ),
        {dimension.key: dimension.status for dimension in dimensions},
    )


def build_dossier(
    *,
    generated_at: datetime | None = None,
) -> ResearchDossier:
    business, dimensions = _business()
    ref = _ref()
    financial_findings = (
        statement(
            "fact",
            "2026H1 营业收入 893.98 亿元、同比 -8.15%；归母净利润 132.78 亿元、同比 -7.87%；扣非归母净利润 127.07 亿元、同比 -8.89%（p.7）。",
            confidence=CONFIDENCE_MEDIUM,
            evidence_refs=[EVIDENCE_ID],
        ),
        statement(
            "fact",
            "2026H1 加权平均净资产收益率 8.68%，同比下降 1.41 个百分点（p.7）。",
            confidence=CONFIDENCE_MEDIUM,
            evidence_refs=[EVIDENCE_ID],
        ),
        statement(
            "fact",
            "2026H1 经营现金流 188.09 亿元、同比 -33.60%；购建长期资产支付现金 7.30 亿元，上年同期 9.86 亿元（p.61）。",
            confidence=CONFIDENCE_MEDIUM,
            evidence_refs=[EVIDENCE_ID],
        ),
        statement(
            "fact",
            "期末货币资金 1,282.48 亿元，其中受限货币资金 139.63 亿元；短期借款 797.19 亿元、长期借款 21.29 亿元（p.25-27,53）。",
            confidence=CONFIDENCE_MEDIUM,
            evidence_refs=[EVIDENCE_ID],
        ),
        statement(
            "interpretation",
            "账面大额现金不能直接等同于可分配净现金；金融资产、受限资金和短期融资需要分层后才能用于估值。",
            confidence=CONFIDENCE_LOW,
            evidence_refs=[EVIDENCE_ID],
        ),
    )
    financial = section(
        "financial_quality",
        "Financial Quality",
        SECTION_COMPLETE,
        findings=financial_findings,
        blockers=(
            "2026 半年报未经审计",
            "财务公司、受限现金、金融资产与有息负债口径未拆分",
            "FCFF 所需的 EBIT、现金税、D&A、净营运资本、WACC 与净债务未形成已注册输入包",
        ),
        explanation="基础财务事实完整；模型输入和法人层级资本归属继续显式保留缺口。",
    )
    capital_findings = (
        statement(
            "fact",
            "公司拟暂不派发 2026 年中期现金红利，后续另行决定中期利润分配（p.2）。",
            confidence=CONFIDENCE_MEDIUM,
            evidence_refs=[EVIDENCE_ID],
        ),
        statement(
            "fact",
            "上市以来累计现金分红超 1,588 亿元；2025 年度累计现金分红 167.87 亿元，占 2025 年度归母净利润 57.88%（p.32）。",
            confidence=CONFIDENCE_MEDIUM,
            evidence_refs=[EVIDENCE_ID],
        ),
        statement(
            "fact",
            "2020 年以来累计回购约 6.17 亿股、金额约 300 亿元；2026 年新一轮回购金额不低于 50 亿元、不超过 100 亿元，70% 以上拟注销（p.32,47）。",
            confidence=CONFIDENCE_MEDIUM,
            evidence_refs=[EVIDENCE_ID],
        ),
        statement(
            "interpretation",
            "历史现金回报记录明确，但当前资本结构中的大额金融资产、短期融资与受限现金使每股可分配现金和净现金评估不能简单化。",
            confidence=CONFIDENCE_LOW,
            evidence_refs=[EVIDENCE_ID],
        ),
    )
    capital = section(
        "capital_allocation",
        "Capital Allocation",
        SECTION_COMPLETE,
        findings=capital_findings,
        blockers=("法人层级可分配现金与金融子/财务公司现金流未映射",),
        explanation="分红、回购和中期不派息事实已核验；资本配置对每股价值的完整影响继续显式保留缺口。",
    )
    thesis = section(
        "thesis",
        "Thesis",
        SECTION_COMPLETE,
        findings=(
            statement(
                "interpretation",
                "研究论点：格力是否能在国内空调需求收缩、价格带下移和海外承压的环境中，依靠品牌、研发、自研制造与渠道维持有质量的盈利，并让工业品第二曲线形成可验证回报。",
                confidence=CONFIDENCE_LOW,
                evidence_refs=[EVIDENCE_ID],
            ),
            statement(
                "interpretation",
                "回报驱动：消费电器产品结构与毛利率、内销渠道稳定性、工业品再投资回报、现金分配与回购。",
                confidence=CONFIDENCE_LOW,
                evidence_refs=[EVIDENCE_ID],
            ),
            statement(
                "gap",
                "误定价假设：当前半年报不能证明市场低估；未注册完整估值前不得把低 ROE 或账面现金直接转为买入理由。",
            ),
        ),
        explanation="论点、回报驱动与误定价假设未建立均已完整表达；工业品分部回报和完整估值仍为后续缺口。",
    )
    counter = section(
        "counter_evidence",
        "Counter Evidence",
        SECTION_COMPLETE,
        findings=(
            statement(
                "fact",
                "收入、归母利润、扣非利润与经营现金流均同比下降；经营现金流降幅 33.60% 明显大于收入降幅（p.7）。",
                confidence=CONFIDENCE_MEDIUM,
                evidence_refs=[EVIDENCE_ID],
            ),
            statement(
                "fact",
                "海外主营收入同比 -21.98%，中东高占比放大地缘冲突冲击；行业出口销量同比 -6.8%（p.9-10,24）。",
                confidence=CONFIDENCE_MEDIUM,
                evidence_refs=[EVIDENCE_ID],
            ),
            statement(
                "fact",
                "合同负债由 152.07 亿元降至 84.74 亿元；消费电器收入同比 -2.89%，毛利率同比下降 1.43 个百分点（p.24-25）。",
                confidence=CONFIDENCE_MEDIUM,
                evidence_refs=[EVIDENCE_ID],
            ),
            statement(
                "fact",
                "研发投入同比 -19.01%；公司解释为主要受项目投入节奏影响，尚不能据此证明研发优势削弱（p.23）。",
                confidence=CONFIDENCE_MEDIUM,
                evidence_refs=[EVIDENCE_ID],
            ),
        ),
    )
    breakers = section(
        "thesis_breakers",
        "Thesis Breakers",
        SECTION_COMPLETE,
        findings=(
            statement(
                "hypothesis",
                "若国内零售持续向低价段迁移，消费电器毛利率与单位经济性进一步下降，则当前“品质与结构”论点受损。",
                confidence=CONFIDENCE_UNKNOWN,
                evidence_refs=[EVIDENCE_ID],
            ),
            statement(
                "hypothesis",
                "若海外地缘风险、渠道库存和自主品牌溢价策略持续压制出口，海外恢复假设需要下调。",
                confidence=CONFIDENCE_UNKNOWN,
                evidence_refs=[EVIDENCE_ID],
            ),
            statement(
                "hypothesis",
                "若合同负债、库存和应收继续显示渠道去库存，经营现金流与销售确认质量需重新审查。",
                confidence=CONFIDENCE_UNKNOWN,
                evidence_refs=[EVIDENCE_ID],
            ),
            statement(
                "hypothesis",
                "若金融资产、受限现金和融资负债无法完成法人层级拆分，则企业/权益价值模型不能解锁。",
                confidence=CONFIDENCE_UNKNOWN,
                evidence_refs=[EVIDENCE_ID],
            ),
        ),
    )
    next_events = section(
        "next_events",
        "Next Events",
        SECTION_COMPLETE,
        findings=(
            statement(
                "fact",
                "观察下一份法定财务报告：收入、分部毛利率、经营现金流、合同负债和库存变化。",
                confidence=CONFIDENCE_MEDIUM,
                evidence_refs=[EVIDENCE_ID],
            ),
            statement(
                "fact",
                "观察 2026 年回购方案的执行、注销或员工持股用途，以及是否宣布中期或年度分红。",
                confidence=CONFIDENCE_MEDIUM,
                evidence_refs=[EVIDENCE_ID],
            ),
            statement(
                "fact",
                "观察工业制品、智能装备与绿色能源分部的连续收入和回报数据，判断第二成长曲线。",
                confidence=CONFIDENCE_MEDIUM,
                evidence_refs=[EVIDENCE_ID],
            ),
            statement(
                "fact",
                "补充财务公司、受限资金、融资负债及法人层级现金流的正式口径，再评估 FCFF 输入。",
                confidence=CONFIDENCE_MEDIUM,
                evidence_refs=[EVIDENCE_ID],
            ),
        ),
    )
    blockers = tuple(
        dict.fromkeys(
            (
                *business.blockers,
                *financial.blockers,
                *capital.blockers,
            )
        )
    )
    gaps = section(
        "research_gaps",
        "Research Gaps",
        SECTION_COMPLETE,
        findings=tuple(
            statement("gap", blocker, status=SECTION_BLOCKED) for blocker in blockers
        ),
        blockers=blockers,
    )
    generated = generated_at or datetime.now(timezone.utc)
    return ResearchDossier(
        schema_version=DOSSIER_SCHEMA_VERSION,
        symbol="000651",
        name="格力电器",
        as_of=date(2026, 9, 23),
        run_id="gree-m1-dossier-v1",
        generated_at=generated,
        research_version="gree-m1-dossier-v1",
        profile_id="mature_manufacturing",
        primary_model="fcff",
        action=ACTION_NO_ORDER,
        business_quality=business,
        financial_quality=financial,
        capital_allocation=capital,
        thesis=thesis,
        counter_evidence=counter,
        thesis_breakers=breakers,
        next_events=next_events,
        research_gaps=gaps,
        evidence_refs=[ref],
        financial_period=date(2026, 6, 30),
        valuation_status="NOT_READY",
        research_status="financial_scope_partial",
    )


def write(generated_at: datetime) -> dict:
    dossier = build_dossier(generated_at=generated_at)
    timestamp = generated_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = ROOT / "runtime" / "company-research" / f"000651-m1-dossier-{timestamp}"
    target.mkdir(parents=True, exist_ok=True)
    evidence = target / "evidence.json"
    evidence.write_text(
        json.dumps(dossier.as_policy(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pointer = {
        "path": str(target.relative_to(ROOT)),
        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
    }
    (ROOT / "runtime/company-research/000651-m1-dossier-latest.json").write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "symbol": dossier.symbol,
        "readiness": dossier.readiness,
        "action": dossier.action,
        "evidence_path": str(evidence.relative_to(ROOT)),
        "source_pdf_sha256": PDF_SHA256,
        **pointer,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()
    result = write(datetime.now(timezone.utc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
