"""Create a source-bound 600887 first-input attempt from archived facts and v4 research.

This adapter does not approve a main valuation or copy a prior valuation result.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runtime/e2-first-input-600887-20261112"
NATIVE = OUT / "native-facts-20261112T110158481972Z.json"
PROPOSAL = ROOT / "config/research-proposals/600887-joint-capital-cash-path-v4.json"
RATIONALE = ROOT / "config/research-assumptions/600887-joint-capital-cash-path-v4.json"


def binding(path: Path) -> dict[str, str]:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write_new(prefix: str, payload: dict, stamp: str) -> Path:
    path = OUT / f"{prefix}-{stamp}.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return path


def main() -> None:
    native = json.loads(NATIVE.read_text(encoding="utf-8"))
    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    facts = {(row["field"], row["period_end"]): row["id"] for row in native["facts"]}
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    source_bindings = [binding(path) for path in (NATIVE, PROPOSAL, RATIONALE)]
    choice = proposal["choices"][0]
    flow_fields = ("revenue", "cost", "surcharges", "selling", "admin", "research", "pre_tax_profit", "tax", "parent_profit")

    def ttm(field: str) -> dict:
        return {"operation": "TTM", "fact_ids": [facts[(field, period)] for period in ("2025-12-31", "2026-06-30", "2025-06-30")]}

    historical = {field: ttm(field) for field in flow_fields}
    historical["nonrecurring"] = {"operation": "DIFFERENCE", "operands": [ttm("parent_profit"), ttm("ex_parent_profit")]}
    historical["da"] = {"operation": "SUM", "operands": [ttm("depreciation"), ttm("amortization")]}
    for field in ("opening_cash", "opening_distribution_capacity", "cash_floor"):
        proposal_item = proposal["joint_historical"][field]
        historical[field] = {"assumption": {"value": proposal_item["value"], "unit": "CNY", "scope": "ordinary_owner_equivalent_cash_mapping", "rationale": proposal_item["rationale"], "source_bindings": source_bindings}}
    assumptions = {
        "schema_version": "first-research-assumptions-v1", "action": "no_order", "symbol": "600887",
        "financial_basis": "2026-06-30", "generated_at": now.isoformat(),
        "assumption_scope": "RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST",
        "source_bindings": source_bindings,
        "choice": {"id": choice["id"], "rationale": choice["rationale"], "countercase": choice["countercase"]},
        "historical_bindings": historical,
        "scenarios": {name: {"drivers": choice["joint_drivers"][name], "terminal_policy": choice["terminal_policy"][name], "cost_of_equity": choice["cost_of_equity"][name]} for name in ("bear", "base", "bull")},
    }
    assumptions_path = write_new("assumptions", assumptions, stamp)
    sources = [row["id"] for row in native["sources"]]
    refs = [{"kind": "interpretation", "text": text, "evidence_refs": sources} for text in (
        "历史经营利润及股东现金渠道可研究，不证明未来现金可达性。",
        "维持投入、营运资金和分配约束可能使未来分红低于目标比例。",
    )]
    spec = {
        "schema_version": "first-research-input-spec-v1", "action": "no_order", "symbol": "600887", "name": "伊利股份",
        "profile_id": "quality_compounder", "run_id": f"first-600887-{stamp}",
        "point_in_time": {"report_period": "2026-06-30", "research_as_of": now.date().isoformat(), "valuation_date": "2026-06-30", "available_at": now.isoformat(), "computed_at": now.isoformat()},
        "native_facts_binding": binding(NATIVE),
        "capital_bindings": {"start_book_equity": facts[("start_book_equity", "2026-06-30")], "ordinary_shares": facts[("ordinary_shares", "2026-06-30")]},
        "share_basis": "issued_ordinary_shares", "assumption_binding": binding(assumptions_path),
        "research_case": {"industry": "乳制品", "investment_path": "历史经营与条件股东现金研究；未批准主估值",
            "thesis": "品牌、渠道和产品结构可能支撑经营现金，仍须逐年检验成本、投入和分配。",
            "return_driver": "经营利润转换为普通股股东可达现金，取决于维持投入和资本配置。",
            "mispricing_hypothesis": "未证明市场定价错误；本次不据现价调整预测。",
            "positives": [refs[0]], "counter_evidence": [refs[1]],
            "thesis_breakers": [{"kind": "hypothesis", "text": "利润无法转换为可达股东现金或持续维持投入高于研究路径。", "evidence_refs": sources}],
            "next_events": [{"kind": "gap", "text": "后续财报中核验母公司现金、分配能力与资本投入。", "evidence_refs": sources}]},
    }
    spec_path = write_new("spec", spec, stamp)
    print(json.dumps({"assumptions": binding(assumptions_path), "spec": binding(spec_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
