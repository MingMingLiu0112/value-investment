#!/usr/bin/env python3
"""Build the bounded second-round research evidence for Moutai's workbook card.

This package deliberately turns previously pinned issuer facts into a small set
of falsifiable research conclusions.  It does not refresh a quote, approve a
valuation model, or create a trading signal.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "runtime/company-research"
CURRENT_MODEL_POINTER = RESEARCH / "600519-consolidated-parent-equity-residual-income-current-latest.json"
VOLUME_PATH = RESEARCH / "600519-volume-constraints-20260909T092256548331Z/evidence.json"
VOLUME_SHA256 = "f33a903584df8b556024716c18746e5a1f0967269b1477ed2cfc044fb5a42f31"
DIAGNOSTIC_PATH = RESEARCH / "600519-current-assumption-diagnostic-20260917T014020Z/evidence.json"
DIAGNOSTIC_SHA256 = "452c3f71fc4f950ff2fe58025d8fb52082174b0efd49961d3b93e0099451ae72"
PEER_PATH = RESEARCH / "000858-peer-interim-20260909T125304973619Z/evidence.json"
PEER_SHA256 = "1e5a3d030881678d7e3b63ae03718df3312dac4a17a44c64fb79436516a7a00c"
GOVERNANCE_POINTER = RESEARCH / "600519-governance-capital-review-latest.json"
RESILIENCE_POINTER = RESEARCH / "600519-resilience-review-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_pinned_path(path: Path, expected: str) -> tuple[dict, dict]:
    if digest(path) != expected:
        raise ValueError(f"Pinned evidence changed: {path}")
    return json.loads(path.read_text(encoding="utf-8")), {
        "path": str(path.relative_to(ROOT)), "sha256": expected,
    }


def read_pointer(path: Path) -> tuple[dict, dict]:
    pointer = json.loads(path.read_text(encoding="utf-8"))
    target = (ROOT / pointer["path"] / "evidence.json").resolve()
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError("Pointer escapes project root")
    return read_pinned_path(target, pointer["sha256"])


def nested_fact(data: dict, *names: str) -> Decimal:
    value = data
    for name in names:
        value = value[name]
    return Decimal(str(value))


def build() -> dict:
    model, model_ref = read_pointer(CURRENT_MODEL_POINTER)
    facts_ref = model["inputs"]["facts"]
    facts_path = (ROOT / facts_ref["path"]).resolve()
    facts, facts_reference = read_pinned_path(facts_path, facts_ref["sha256"])
    policy_ref = model["policy"]
    policy, policy_reference = read_pinned_path((ROOT / policy_ref["path"]).resolve(), policy_ref["sha256"])
    volume, volume_reference = read_pinned_path(VOLUME_PATH, VOLUME_SHA256)
    diagnostic, diagnostic_reference = read_pinned_path(DIAGNOSTIC_PATH, DIAGNOSTIC_SHA256)
    peer, peer_reference = read_pinned_path(PEER_PATH, PEER_SHA256)
    governance, governance_reference = read_pointer(GOVERNANCE_POINTER)
    resilience, resilience_reference = read_pointer(RESILIENCE_POINTER)

    current = facts["current_disclosed_basis"]
    facts_period = current["period_end"]
    profit = Decimal(str(current["parent_profit_h1_cny"]))
    ttm_profit = Decimal(str(current["ttm_ex_nonrecurring_parent_profit_cny"]))
    payout_text = policy["rationale"]["payout"]
    if "15,224,606,455.02" not in payout_text or "35,032,574,305.20" not in payout_text:
        raise ValueError("Current policy no longer contains the registered cash-flow extract")
    cfo = Decimal("15224606455.02")
    capex = Decimal("828677952.16")
    distributions = Decimal("35032574305.20")
    coverage = (cfo - capex) / distributions

    revenue_change = Decimal(str(volume["reported_revenue_growth_pct"]))
    sales_volume_change = Decimal(str(volume["reported_sales_volume_growth_pct"]))
    unit_change = Decimal(str(volume["approximate_revenue_per_tonne_change"])) * Decimal("100")
    reverse_rows = diagnostic["reverse_valuation"]
    if not reverse_rows or any(row["status"] != "above_registered_envelope" for row in reverse_rows):
        raise ValueError("Valuation diagnostic scope changed")
    if peer.get("peer_support_approved") is not False:
        raise ValueError("Peer evidence cannot become supporting evidence automatically")
    if (governance.get("symbol") != "600519"
            or governance.get("review_version") != "moutai-governance-capital-review-v1"
            or governance.get("governance_approved") is not False):
        raise ValueError("Governance review scope changed")
    if (resilience.get("symbol") != "600519"
            or resilience.get("review_version") != "moutai-resilience-review-v1"
            or resilience.get("resilience_approved") is not False):
        raise ValueError("Resilience review scope changed")

    return {
        "symbol": "600519",
        "research_card_version": "moutai-research-card-evidence-v5",
        "as_of": model["valuation_at"][:10],
        "scope": "second-round company research: earnings quality, sales realization, cash distribution and valuation applicability; not a target price or trading recommendation",
        "evidence": {
            "current_model": model_ref,
            "issuer_interim_facts": facts_reference,
            "policy_extract": policy_reference,
            "fy2025_volume_constraints": volume_reference,
            "valuation_diagnostic": diagnostic_reference,
            "peer_counterevidence": peer_reference,
            "governance_capital_review": governance_reference,
            "resilience_review": resilience_reference,
        },
        "facts": {
            "period_end": facts_period,
            "parent_profit_h1_cny": str(profit),
            "ttm_ex_nonrecurring_parent_profit_cny": str(ttm_profit),
            "liquor_revenue_growth_pct": str(revenue_change),
            "liquor_sales_volume_growth_pct": str(sales_volume_change),
            "approx_revenue_per_tonne_change_pct": str(unit_change),
            "parent_cfo_h1_cny": str(cfo),
            "parent_capex_h1_cny": str(capex),
            "parent_distribution_and_interest_h1_cny": str(distributions),
            "parent_cfo_after_capex_coverage_of_distribution": str(coverage),
        },
        "conclusions": {
            "business_model": "高端白酒销售的研究核心是销量、实现价格/产品结构和渠道，而不是产能或品牌标签本身。",
            "earnings": "公司仍保持高额盈利，但FY2025归母利润和2026上半年归母利润均下降；盈利恢复尚未被证明。",
            "sales_realization": "FY2025白酒销量增长而收入下降，收入/吨的近似指标下降。仅凭产量、库存或销量增长，不能推出价格和利润会恢复。",
            "cash_distribution": "2026上半年母公司经营现金流扣除购建长期资产后，约覆盖当期分红及利息支出的41.1%。这要求结合期初现金、季节性及子公司汇款复核，不能据此直接判定分红不可持续。",
            "resilience": resilience["conclusions"]["resilience"],
            "liquidity_boundary": resilience["conclusions"]["liquidity_boundary"],
            "resilience_counterevidence": resilience["conclusions"]["counterevidence"],
            "counterevidence": "五粮液中报可作为行业并未自动复苏的旁证，但不能把其现金流比例或经营结果直接外推给茅台。",
            "capital_allocation": governance["conclusions"]["capital_allocation"],
            "governance": governance["conclusions"]["governance"],
            "governance_counterevidence": governance["conclusions"]["counterevidence"],
            "model_basis": "主研究模型为归母权益剩余收益/分配能力模型：以2026年中期归母权益和扣非TTM为起点，分别检验未来五年利润-5%/0/+5%、75%研究性分配率、优势回报五年衰减至资本成本及不同折现率。它的作用是把盈利、资本和分配假设放在同一口径下比较，不是正式合理价值。",
            "market_implied_expectation": "在已登记的强衰减逆向检验中，归档价格高于0年、5年和10年优势衰减，以及利润增长-5%至+5%的所有注册组合上限。因此，价格至少要求利润路径、可分配比例、优势持续期或资本成本中的一项显著强于该保守组合；但这些变量存在多解，不能反推出唯一市场预测。",
            "valuation": "上述价格约束提示不能把归档报价视为已证实的安全边际；它不是合理价、卖出结论或单一市场预期。正式估值仍须通过股本/资本动作、预测假设和折现政策的指定日期审查。",
        },
        "conditional_actions": {
            "not_holding": "不从旧情景值或价格下跌直接得出买入价。先补足量价兑现、全年可分配现金和优势持续期证据，再冻结适用估值模型。",
            "holding": "先核对自己的成本、仓位和现金需求；重点复评量价兑现、分配能力和治理/资本配置。系统或数据执行故障不是卖出依据。",
        },
        "next_event": "下一份定期报告及任何渠道、价格策略、分红/回购或重大资本动作披露；更新时须重算而非沿用本轮结论。",
        "gaps": [
            "量价与渠道：下一期收入、销量、产品/渠道结构须验证FY2025收入/吨下行是阶段性还是持续性。",
            "可分配现金：须以全年经营现金流、必要投入、受限资金及母子公司现金归属复核分配能力。",
            "优势持续期：须用公司经营证据和可比公司反证约束主模型的增长、回报率和衰减期限。",
        ],
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
    }


def main() -> int:
    result = build()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = RESEARCH / f"600519-research-card-evidence-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = RESEARCH / "600519-research-card-evidence-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "research_card_version": result["research_card_version"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
