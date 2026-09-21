"""Build a single research-only ValuationResult through a shared model."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from value_investment_agent.research_case import ResearchCase
from value_investment_agent.valuation_models.fcff import FCFFValuationModel, FinancialFacts

ROOT = Path(__file__).resolve().parents[1]


def _reference(ref_id: str, path: Path) -> dict[str, str]:
    return {"id": ref_id, "path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _case(payload: dict, symbol: str) -> ResearchCase:
    for record in payload["records"]:
        if record["case"]["symbol"] == symbol:
            raw = record["case"].copy()
            for key in ("as_of", "quote_date", "financial_period"):
                if raw.get(key):
                    raw[key] = date.fromisoformat(raw[key])
            from datetime import datetime
            raw["generated_at"] = datetime.fromisoformat(raw["generated_at"])
            return ResearchCase(**raw)
    raise ValueError(f"ResearchCase not found: {symbol}")


def build(*, symbol: str, case_path: Path, facts_path: Path) -> dict:
    case = _case(json.loads(case_path.read_text(encoding="utf-8")), symbol)
    audit = json.loads(facts_path.read_text(encoding="utf-8"))
    facts = FinancialFacts(
        symbol=symbol, as_of=date.fromisoformat(audit["as_of_period"]),
        verified=audit["financial_scope_approved"] is True,
        evidence_refs=[_reference("financial_scope", facts_path)],
        blockers=list(audit.get("per_share_blockers", [])),
    )
    result = FCFFValuationModel().value(facts, case)
    return {"version": "unified-company-valuation-result-v1", "result": json.loads(result.to_json()),
            "research_case_ref": _reference("excel_mvp_research_cases", case_path),
            "formal_fair_value": None, "trade_approved": False, "live_eligible": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--facts-path", required=True)
    parser.add_argument("--case-path", default="runtime/excel-mvp-research-cases/evidence.json")
    args = parser.parse_args()
    case_path = (ROOT / args.case_path).resolve()
    facts_path = (ROOT / args.facts_path).resolve()
    if not case_path.is_relative_to(ROOT.resolve()) or not facts_path.is_relative_to(ROOT.resolve()):
        raise ValueError("Inputs must stay within the project root")
    output = ROOT / "runtime/valuation-results" / f"{args.symbol}-fcff-stage-b"
    output.mkdir(parents=True, exist_ok=True)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(build(symbol=args.symbol, case_path=case_path, facts_path=facts_path), ensure_ascii=False, indent=2), encoding="utf-8")
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    (ROOT / "runtime/valuation-results" / f"{args.symbol}-fcff-stage-b-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"path": str(evidence), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
