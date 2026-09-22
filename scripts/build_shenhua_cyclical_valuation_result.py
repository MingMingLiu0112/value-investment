"""Produce Shenhua's fail-closed cyclical-normalized ValuationResult."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.research_case import ResearchCase
from value_investment_agent.price_bridge import pending_price_bridge_for_incomplete_valuation
from value_investment_agent.research_profile import PROFILES
from value_investment_agent.valuation_models.cyclical import CyclicalFacts, CyclicalNormalizedValuationModel
from value_investment_agent.valuation_router import ROUTE_SUPPORTED, ValuationRouter


SOURCE = ROOT / "runtime" / "shenhua-2025-official.pdf"
SCOPE = ROOT / "runtime" / "company-research" / "shenhua-cyclical-scope-20260921" / "evidence.json"
OUT = ROOT / "runtime" / "valuation-results" / "601088-cyclical-b3"
POINTER = ROOT / "runtime" / "valuation-results" / "601088-cyclical-stage-b-latest.json"


def evidence_ref(ref_id: str, path: Path, description: str) -> dict:
    return {"id": ref_id, "path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "description": description}


def build_case() -> ResearchCase:
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    scope_hash = hashlib.sha256(SCOPE.read_bytes()).hexdigest()
    return ResearchCase(
        symbol="601088", name="中国神华", as_of=date(2026, 9, 21),
        run_id="shenhua-b3-20260921", generated_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        research_version="shenhua-b3-v1", industry="煤炭与综合能源",
        investment_path="周期正常化 / 现金回报",
        thesis="煤炭、发电、运输及煤化工一体化能否在周期回落时保持可分配现金，需要中周期价格、成本、资源寿命和资本开支共同验证。",
        return_driver="穿越周期的可分配现金与资本配置，不预设高点利润永久化。",
        mispricing_hypothesis="未建立；尚无已验证的中周期正常化盈利来推断市场隐含假设。",
        financial_summary={"period_end": "2025-12-31",
                           "parent_attributable_profit_cny": "52849000000",
                           "operating_cash_flow_cny": "75059000000",
                           "coal_segment_profit_cny": "46597000000",
                           "valuation_status": "not_ready"},
        positives=[], counter_evidence=[], thesis_breakers=[], next_events=[],
        evidence_status="verified", valuation_status="not_ready",
        research_status="financial_scope_partial",
        blockers=["mid_cycle_cyclical_inputs_not_verified"],
        evidence_refs=[
            evidence_ref("shenhua_cyclical_scope_case", SCOPE, description="2025年报周期口径审计"),
            {"id": "shenhua_2025_official", "path": "runtime/shenhua-2025-official.pdf",
             "sha256": source_hash, "description": "交易所披露的2025年度报告原件"},
        ],
        quote_date=None, financial_period=date(2025, 12, 31),
        missing_date_reasons={"quote_date": "周期估值阶段不使用行情生成结论。"},
    )


def main() -> None:
    route = ValuationRouter().route(PROFILES["cyclical_cash_return"])
    if (route.status != ROUTE_SUPPORTED
            or route.model_type != "cyclical_normalized"
            or route.facts_contract is not CyclicalFacts):
        raise ValueError("Cyclical profile routing rejected the registered Shenhua model")
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    case = build_case()
    facts = CyclicalFacts(
        symbol="601088", as_of=date(2025, 12, 31), verified=False, confidence="低",
        evidence_refs=[evidence_ref("shenhua_cyclical_scope", SCOPE, description="2025年报周期口径审计")],
        blockers=list(scope["blockers"]),
        operating_inputs={name: None for name in CyclicalFacts.REQUIRED_CYCLICAL_INPUTS},
    )
    result = CyclicalNormalizedValuationModel().value(facts, case)
    price_bridge = pending_price_bridge_for_incomplete_valuation(
        result,
        evidence_refs=list(result.evidence_refs),
    )
    payload = {
        "version": "unified-company-valuation-result-v1",
        "model": "cyclical_normalized",
        "result": json.loads(result.to_json()),
        "price_bridge": json.loads(price_bridge.to_json()),
        "formal_fair_value": None,
        "trade_approved": False,
        "live_eligible": False,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    POINTER.write_text(
        json.dumps({"path": str(OUT.relative_to(ROOT)), "sha256": digest}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                      "status": payload["result"]["status"], "valuation_route": route.as_policy()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
