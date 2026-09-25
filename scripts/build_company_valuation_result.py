"""Build a single research-only ValuationResult through a shared model."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from value_investment_agent.research_profile import PROFILES
from value_investment_agent.application.valuation import (
    build_company_valuation_result,
)

ROOT = Path(__file__).resolve().parents[1]


def build(
    *,
    symbol: str,
    case_path: Path,
    facts_path: Path,
    model: str,
    profile_id: str | None = None,
    applicability_path: Path | None = None,
) -> dict:
    """Backward-compatible import surface for historical tests and callers."""

    return build_company_valuation_result(
        root=ROOT,
        symbol=symbol,
        case_path=case_path,
        facts_path=facts_path,
        model=model,
        profile_id=profile_id,
        applicability_path=applicability_path,
    )


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
    payload = build_company_valuation_result(
        root=ROOT,
        symbol=args.symbol,
        case_path=case_path,
        facts_path=facts_path,
        model=args.model,
        profile_id=args.profile_id,
        applicability_path=applicability_path,
    )
    evidence.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    (ROOT / "runtime/valuation-results" / f"{args.symbol}-fcff-stage-b-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"path": str(evidence), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
