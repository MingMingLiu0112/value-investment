"""Build a standalone simulated M4 portfolio-risk Excel candidate."""
from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import json
from pathlib import Path

from value_investment_agent.m4_portfolio_risk_workbook import (
    write_portfolio_risk_workbook,
)
from value_investment_agent.portfolio_contracts import (
    portfolio_input_bundle_from_payload,
)
from value_investment_agent.portfolio_risk import (
    ASSESSMENT_NAMESPACE_SIMULATED,
    PortfolioRiskAssessment,
    build_portfolio_risk_assessment,
    security_risk_attributes_from_payload,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "tests" / "fixtures" / "m4_portfolio_risk_demo.json"
SCHEMA_VERSION = "m4-portfolio-risk-demo-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "A股价值投资_M4组合风险候选_20260924.xlsx",
    )
    return parser.parse_args()


def load_input(path: Path) -> tuple[dict, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("M4 risk input must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unknown M4 risk input schema")
    if payload.get("action") != "no_order":
        raise ValueError("M4 risk input must remain no_order")
    if payload.get("assessment_namespace") != ASSESSMENT_NAMESPACE_SIMULATED:
        raise ValueError("Public M4 risk candidate must be simulated")
    return payload, {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def build_assessment(payload: dict) -> PortfolioRiskAssessment:
    bundle = portfolio_input_bundle_from_payload(
        {
            "policy": payload["policy"],
            "snapshot": payload["snapshot"],
            "action": "no_order",
        }
    )
    attributes = {
        symbol: security_risk_attributes_from_payload(item)
        for symbol, item in payload["security_attributes"].items()
    }
    return build_portfolio_risk_assessment(
        bundle=bundle,
        security_attributes=attributes,
        as_of=date.fromisoformat(str(payload["as_of"])),
        generated_at=datetime.fromisoformat(str(payload["generated_at"])),
        assessment_id=str(payload["assessment_id"]),
        assessment_namespace=str(payload["assessment_namespace"]),
    )


def main() -> int:
    args = parse_args()
    payload, input_receipt = load_input(args.input.resolve())
    assessment = build_assessment(payload)
    result = write_portfolio_risk_workbook(
        assessment,
        output=args.output,
        root=args.output.resolve().parent,
        security_names=payload.get("security_names"),
    )
    manifest = {
        **result,
        "schema_version": SCHEMA_VERSION,
        "assessment_id": assessment.assessment_id,
        "generated_at": assessment.generated_at.isoformat(),
        "input": input_receipt,
        "finding_kinds": [item.kind for item in assessment.findings()],
    }
    args.output.resolve().with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
