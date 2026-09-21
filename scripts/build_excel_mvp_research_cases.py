"""Build the Stage-A research cases from pinned, retained evidence only."""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path

from value_investment_agent.research_case import ResearchCase
from value_investment_agent.research_gate import evaluate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime" / "excel-mvp-research-cases"
POINTER = ROOT / "runtime" / "excel-mvp-research-cases-latest.json"
TZ = timezone(timedelta(hours=8))


def reference(ref_id: str, path: str, *, description: str) -> dict[str, str]:
    target = ROOT / path
    return {"id": ref_id, "path": path, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "description": description}


def cases() -> list[ResearchCase]:
    moutai_path = "runtime/company-research/600519-research-card-evidence-20260920T035046Z/evidence.json"
    midea_path = "runtime/company-research/midea-admission-audit-20260912T060015556280Z/evidence.json"
    midea_financial = "runtime/company-research/midea-financial-scope-audit-20260912T054916602476Z/evidence.json"
    shenhua_execution = "runtime/strategy-validation/shenhua-real-execution-contract-20260912T060850Z/summary.json"
    shenhua_readiness = "docs/historical-financial-readiness.md"
    generated = datetime(2026, 9, 21, 12, 0, tzinfo=TZ)
    return [
        ResearchCase(
            symbol="600519", name="贵州茅台", as_of=date(2026, 9, 16), run_id="excel-mvp-20260921",
            generated_at=generated, research_version="excel-mvp-v1", industry="高端白酒",
            investment_path="成熟优质复利 + 现金回报", thesis="品牌、渠道与产品结构是否能支撑长期盈利与每股现金回报，仍须以量价和现金归属持续检验。",
            return_driver="盈利持续性、现金分配及资本配置；估值重评不预设。", mispricing_hypothesis="尚未证明市场低估；逆向检验存在多解，不能反推唯一市场预期。",
            financial_summary={"period_end": "2026-06-30", "parent_equity_cny": "251253594419.50", "ttm_ex_nonrecurring_parent_profit_cny": "81367067677.44", "liquor_revenue_growth_pct": "-1.08", "liquor_sales_volume_growth_pct": "2.13"},
            positives=[{"kind":"fact", "text":"已归档2026年中报归母权益与扣非TTM利润锚。", "evidence_refs":["moutai_card"]}, {"kind":"interpretation", "text":"高端白酒的量价和产品结构是商业质量的关键验证线。", "evidence_refs":["moutai_card"]}],
            counter_evidence=[{"kind":"fact", "text":"FY2025白酒收入同比-1.08%，销量同比+2.13%；不能仅凭总量确认价格或结构。", "evidence_refs":["moutai_card"]}, {"kind":"gap", "text":"尚缺渠道库存、批价及产品结构的独立持续性证据。", "evidence_refs":[]}],
            thesis_breakers=[{"kind":"hypothesis", "text":"若量价、渠道或分配能力的后续证据持续恶化，应重新审查盈利持续性和优势期限。", "evidence_refs":[]}],
            next_events=[{"kind":"fact", "text":"下一份定期报告及重大资本动作披露是预先登记的复核事件。", "evidence_refs":["moutai_card"]}],
            evidence_status="verified", valuation_status="not_ready", research_status="financial_scope_approved", blockers=["优势持续期与可分配现金证据未闭合", "正式估值未获批准"],
            evidence_refs=[reference("moutai_card", moutai_path, description="茅台研究卡及其指向的公告、Hash和反证材料")], quote_date=None, financial_period=date(2026,6,30), missing_date_reasons={"quote_date":"本阶段未引入可用于结论的同日行情；不以旧报价产生买卖判断。"}),
        ResearchCase(
            symbol="000333", name="美的集团", as_of=date(2026, 9, 12), run_id="excel-mvp-20260921",
            generated_at=generated, research_version="excel-mvp-v1", industry="家电与智能制造", investment_path="成长价值 / 成熟经营", thesis="规模、产品结构、海外与再投资回报需要由完整财务口径和商业证据共同验证。",
            return_driver="经营效率、再投资和每股价值增长；暂不把利润规模转换为每股价值。", mispricing_hypothesis="尚未建立；不能以未核验股本分母推导EPS、合理价或安全边际。",
            financial_summary={"period_end":"2025-09-30", "research_ttm_parent_attributable_net_income_cny":"44721506000", "scope":"仅作已勾稽研究事实，不是独立核验的每股财务输入"},
            positives=[{"kind":"fact", "text":"已勾稽归母TTM利润规模，可用于趋势与规模研究。", "evidence_refs":["midea_financial"]}],
            counter_evidence=[{"kind":"fact", "text":"加权普通股、A/H及库存股分母未核验，因此每股估值被阻断。", "evidence_refs":["midea_financial", "midea_admission"]}, {"kind":"gap", "text":"本阶段未形成独立商业模式、行业竞争与治理证据链。", "evidence_refs":[]}],
            thesis_breakers=[{"kind":"hypothesis", "text":"在利润、股本和业务驱动未独立核验前，不建立增长或回报的正式论点。", "evidence_refs":[]}],
            next_events=[{"kind":"fact", "text":"先补齐加权股本、A/H及库存股口径，再决定是否建立每股估值模型。", "evidence_refs":["midea_financial", "midea_admission"]}],
            evidence_status="partial", valuation_status="not_ready", research_status="financial_scope_blocked", blockers=["加权普通股未核验", "A/H及库存股分母未批准", "财务来源独立性未验证", "正式估值不存在"],
            evidence_refs=[reference("midea_admission",midea_path,description="美的准入审计"), reference("midea_financial",midea_financial,description="美的财务口径审计")], quote_date=None, financial_period=date(2025,9,30), missing_date_reasons={"quote_date":"本阶段不使用行情生成结论。"}),
        ResearchCase(
            symbol="601088", name="中国神华", as_of=date(2026, 9, 12), run_id="excel-mvp-20260921",
            generated_at=generated, research_version="excel-mvp-v1", industry="煤炭与综合能源", investment_path="周期正常化", thesis="需验证中周期供需、成本曲线、资源寿命、资本开支和低谷现金生存；当前尚未形成基本面论点。",
            return_driver="若后续研究成立，回报应来自中周期现金流和资本配置，而不是高峰期低PE的机械外推。", mispricing_hypothesis="未建立。",
            financial_summary={"status":"本阶段未纳入可追溯的当前财务数值", "historical_note":"2024年报BVPS页面已读，但归属口径与历史可用性未获批准"},
            positives=[{"kind":"fact", "text":"已归档2,600个历史日线会话和复牌约束，可用于后续执行机制研究。", "evidence_refs":["shenhua_execution"]}],
            counter_evidence=[{"kind":"fact", "text":"历史执行输入不含现金分配处理，也不构成价值信号或订单。", "evidence_refs":["shenhua_execution"]}, {"kind":"gap", "text":"当前财务、商业结构、周期位置和资本配置的原始披露证据尚未归档。", "evidence_refs":[]}],
            thesis_breakers=[{"kind":"hypothesis", "text":"在低谷现金流、资源与成本、供需及资本开支证据完成前，任何周期正常化结论均不可成立。", "evidence_refs":[]}],
            next_events=[{"kind":"fact", "text":"先建立当前年报/中报的可追溯财务与业务证据包，再选择周期正常化模型。", "evidence_refs":["shenhua_readiness"]}],
            evidence_status="partial", valuation_status="not_ready", research_status="incomplete", blockers=["当前财务证据包未建立", "周期正常化输入未建立", "正式估值不存在"],
            evidence_refs=[reference("shenhua_execution",shenhua_execution,description="神华历史执行输入合同"), reference("shenhua_readiness",shenhua_readiness,description="历史财务口径准备度记录")], quote_date=None, financial_period=None, missing_date_reasons={"quote_date":"本阶段不使用行情生成结论。", "financial_period":"当前财务原始披露未完成准入，不能从旧表补填。"}),
    ]


def build() -> dict:
    records=[]
    for case in cases():
        gate=evaluate(case)
        records.append({"case": json.loads(case.to_json()), "gate": {"results": gate.results, "blockers": gate.blockers, "conclusion": gate.conclusion}})
    payload={"version":"excel-mvp-research-cases-v1", "generated_at":"2026-09-21T12:00:00+08:00", "records":records, "formal_trade_instructions":False}
    OUT.mkdir(parents=True, exist_ok=True)
    target=OUT/"evidence.json"; target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    POINTER.write_text(json.dumps({"path":str(target.parent.relative_to(ROOT)),"sha256":digest},ensure_ascii=False,indent=2),encoding="utf-8")
    return payload

if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
