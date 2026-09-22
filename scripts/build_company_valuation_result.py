"""Build a single research-only ValuationResult through a shared model."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from value_investment_agent.research_case import ResearchCase
from value_investment_agent.price_bridge import pending_price_bridge_for_incomplete_valuation
from value_investment_agent.research_profile import PROFILES
from value_investment_agent.valuation_models.fcff import FCFFValuationModel, FinancialFacts
from value_investment_agent.valuation_router import ROUTE_SUPPORTED, ValuationRouter

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


def build(*, symbol: str, case_path: Path, facts_path: Path, model: str,
          profile_id: str | None = None, applicability_path: Path | None = None) -> dict:
    if model != "fcff":
        raise ValueError("Only the explicitly selected fcff model is supported")
    route = None
    if profile_id is not None:
        if profile_id not in PROFILES:
            raise ValueError(f"Unknown research profile: {profile_id}")
        route = ValuationRouter().route(PROFILES[profile_id], model)
        if route.status != ROUTE_SUPPORTED or route.model_type != "FCFF":
            raise ValueError(f"Profile {profile_id} does not support the selected FCFF model")
    case = _case(json.loads(case_path.read_text(encoding="utf-8")), symbol)
    audit = json.loads(facts_path.read_text(encoding="utf-8"))
    facts = FinancialFacts(
        symbol=symbol, as_of=date.fromisoformat(audit["as_of_period"]),
        verified=audit["financial_scope_approved"] is True,
        evidence_refs=[_reference("financial_scope", facts_path)],
        blockers=list(audit.get("per_share_blockers", [])),
        operating_inputs={key: (None if value is None else Decimal(str(value)))
                          for key, value in audit.get("fcff_inputs", {}).items()},
    )
    result = FCFFValuationModel().value(facts, case)
    price_bridge = pending_price_bridge_for_incomplete_valuation(
        result,
        evidence_refs=list(result.evidence_refs),
    )
    payload = {
        "version": "unified-company-valuation-result-v1",
        "model": model,
        "result": json.loads(result.to_json()),
        "price_bridge": json.loads(price_bridge.to_json()),
        "research_case_ref": _reference("excel_mvp_research_cases", case_path),
        "formal_fair_value": None,
        "trade_approved": False,
        "live_eligible": False,
    }
    if route is not None:
        payload["valuation_route"] = route.as_policy()
    if applicability_path is not None:
        if route is None:
            raise ValueError("Applicability evidence requires an explicit --profile-id")
        applicability = json.loads(applicability_path.read_text(encoding="utf-8"))
        if (applicability.get("symbol") != symbol
                or applicability.get("profile_route", {}).get("profile_id") != route.profile_id
                or applicability.get("profile_route", {}).get("model_type") != route.model_type):
            raise ValueError("Valuation applicability does not match the selected profile route")
        payload["valuation_applicability"] = {
            "path": str(applicability_path.relative_to(ROOT)),
            "sha256": hashlib.sha256(applicability_path.read_bytes()).hexdigest(),
            "policy": applicability,
        }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--facts-path", required=True)
    parser.add_argument("--case-path", default="runtime/excel-mvp-research-cases/evidence.json")
    parser.add_argument("--model", required=True, choices=["fcff"])
    parser.add_argument("--profile-id", choices=tuple(PROFILES))
    parser.add_argument("--applicability-path", type=Path)
    args = parser.parse_args()
    case_path = (ROOT / args.case_path).resolve()
    facts_path = (ROOT / args.facts_path).resolve()
    applicability_path = (ROOT / args.applicability_path).resolve() if args.applicability_path else None
    if not case_path.is_relative_to(ROOT.resolve()) or not facts_path.is_relative_to(ROOT.resolve()):
        raise ValueError("Inputs must stay within the project root")
    if applicability_path is not None and not applicability_path.is_relative_to(ROOT.resolve()):
        raise ValueError("Applicability evidence must stay within the project root")
    output = ROOT / "runtime/valuation-results" / f"{args.symbol}-fcff-stage-b"
    output.mkdir(parents=True, exist_ok=True)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(build(symbol=args.symbol, case_path=case_path, facts_path=facts_path,
                                         model=args.model, profile_id=args.profile_id,
                                         applicability_path=applicability_path), ensure_ascii=False, indent=2), encoding="utf-8")
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    (ROOT / "runtime/valuation-results" / f"{args.symbol}-fcff-stage-b-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"path": str(evidence), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
