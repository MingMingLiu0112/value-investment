"""Build a standalone simulated M4 position-and-dividend Excel candidate."""
from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import json
from pathlib import Path

from value_investment_agent.dividend_income_projection import (
    NAMESPACE_SIMULATED,
    PortfolioDividendIncomeProjection,
    build_portfolio_dividend_income_projection,
    security_dividend_income_projection_from_payload,
)
from value_investment_agent.m4_guidance_income_workbook import (
    write_guidance_income_workbook,
)
from value_investment_agent.portfolio_contracts import (
    portfolio_input_bundle_from_payload,
)
from value_investment_agent.position_guidance import (
    PositionGuidanceResult,
    build_position_guidance,
    position_candidate_from_payload,
    position_tier_policy_from_payload,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "tests" / "fixtures" / "m4_guidance_income_demo.json"
SCHEMA_VERSION = "m4-guidance-income-demo-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "A股价值投资_M4仓位与股息候选_20260924.xlsx",
    )
    return parser.parse_args()


def load_input(path: Path) -> tuple[dict, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("M4 guidance input must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unknown M4 guidance input schema")
    if payload.get("action") != "no_order":
        raise ValueError("M4 guidance input must remain no_order")
    if payload.get("assessment_namespace") != NAMESPACE_SIMULATED:
        raise ValueError("Public M4 guidance candidate must be simulated")
    return payload, {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def build_models(
    payload: dict,
) -> tuple[PositionGuidanceResult, PortfolioDividendIncomeProjection]:
    bundle = portfolio_input_bundle_from_payload(
        {
            "policy": payload["policy"],
            "snapshot": payload["snapshot"],
            "action": "no_order",
        }
    )
    tier_policy = position_tier_policy_from_payload(payload["tier_policy"])
    candidates = {
        symbol: position_candidate_from_payload(item)
        for symbol, item in payload["candidates"].items()
    }
    security_projections = {
        symbol: security_dividend_income_projection_from_payload(item)
        for symbol, item in payload["security_projections"].items()
    }
    as_of = date.fromisoformat(str(payload["as_of"]))
    generated_at = datetime.fromisoformat(str(payload["generated_at"]))
    guidance = build_position_guidance(
        bundle=bundle,
        tier_policy=tier_policy,
        candidates=candidates,
        as_of=as_of,
        generated_at=generated_at,
        assessment_id=str(payload["assessment_id"]),
        assessment_namespace=NAMESPACE_SIMULATED,
    )
    dividend = build_portfolio_dividend_income_projection(
        bundle=bundle,
        security_projections=security_projections,
        as_of=as_of,
        generated_at=generated_at,
        assessment_id=str(payload["assessment_id"]),
        assessment_namespace=NAMESPACE_SIMULATED,
    )
    return guidance, dividend


def main() -> int:
    args = parse_args()
    payload, input_receipt = load_input(args.input.resolve())
    guidance, dividend = build_models(payload)
    result = write_guidance_income_workbook(
        guidance,
        dividend,
        output=args.output,
        root=args.output.resolve().parent,
        security_names=payload.get("security_names"),
    )
    manifest = {
        **result,
        "schema_version": SCHEMA_VERSION,
        "assessment_id": str(payload["assessment_id"]),
        "generated_at": guidance.generated_at.isoformat(),
        "input": input_receipt,
        "guidance_blockers": [line.blockers for line in guidance.lines()],
        "dividend_blockers": list(dividend.blockers()),
    }
    args.output.resolve().with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
