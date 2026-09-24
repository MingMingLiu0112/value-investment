"""Build a standalone simulated M4/M5 joint Checkpoint C Excel candidate."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_m4_guidance_income_candidate import (
    build_models as build_guidance_income_models,
    load_input as load_guidance_income_input,
)
from scripts.build_m4_portfolio_risk_candidate import (
    build_assessment as build_risk_assessment,
    load_input as load_risk_input,
)
from scripts.build_m5_event_infrastructure_candidate import (
    build_models as build_m5_event_models,
)
from value_investment_agent.investment_decision import ACTION_NO_ORDER
from value_investment_agent.dividend_income_projection import (
    PortfolioDividendIncomeProjection,
)
from value_investment_agent.m4_m5_integration import (
    M4M5IntegrationResult,
    STATUS_PARTIAL,
    STATUS_READY,
    build_m4_m5_integration,
    integration_artifact_definition_from_payload,
)
from value_investment_agent.m4_m5_integration_workbook import (
    write_m4_m5_integration_workbook,
)
from value_investment_agent.m5_event_core import NAMESPACE_SIMULATED
from value_investment_agent.m5_event_dependencies import dependency_graph_from_payload
from value_investment_agent.portfolio_risk import PortfolioRiskAssessment
from value_investment_agent.position_guidance import PositionGuidanceResult


DEFAULT_INPUT = ROOT / "tests" / "fixtures" / "m4_m5_integrated_demo.json"
SCHEMA_VERSION = "m4-m5-integration-demo-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "A股价值投资_M4M5联合检查点候选_20260924.xlsx",
    )
    return parser.parse_args()


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def load_input(path: Path) -> tuple[dict, dict]:
    path = path.resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("M4/M5 integration input must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unknown M4/M5 integration input schema")
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("M4/M5 integration input must remain no_order")
    if payload.get("assessment_namespace") != NAMESPACE_SIMULATED:
        raise ValueError("Public M4/M5 integration candidate must be simulated")

    risk_path = (
        ROOT
        / _require_text(payload.get("m4_risk_input"), "m4_risk_input")
    ).resolve()
    guidance_path = (
        ROOT
        / _require_text(payload.get("m4_guidance_input"), "m4_guidance_input")
    ).resolve()
    m5_payload = dict(payload["m5"])
    if m5_payload.get("schema_version") != "m5-event-demo-v1":
        raise ValueError("Unknown embedded M5 input schema")
    if m5_payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("Embedded M5 input must remain no_order")
    if m5_payload.get("namespace") != NAMESPACE_SIMULATED:
        raise ValueError("Embedded M5 input must be simulated")

    input_files = (path, risk_path, guidance_path)
    input_receipts = {
        item.name: {
            "path": str(item),
            "sha256": hashlib.sha256(item.read_bytes()).hexdigest(),
        }
        for item in input_files
    }
    return payload, input_receipts


def _baseline_status(domain_status: str) -> str:
    if domain_status in {"PASS", "READY"}:
        return STATUS_READY
    return STATUS_PARTIAL


def build_models(
    payload: dict,
    *,
    base_dir: Path | None = None,
) -> tuple[
    M4M5IntegrationResult,
    PortfolioRiskAssessment,
    PositionGuidanceResult,
    PortfolioDividendIncomeProjection,
    dict,
]:
    root = (base_dir or ROOT).resolve()
    risk_payload, risk_receipt = load_risk_input(
        (root / payload["m4_risk_input"]).resolve()
    )
    risk = build_risk_assessment(risk_payload)
    guidance_payload, guidance_receipt = load_guidance_income_input(
        (root / payload["m4_guidance_input"]).resolve()
    )
    guidance, dividend = build_guidance_income_models(guidance_payload)
    m5_receipt, watermark = build_m5_event_models(payload["m5"])
    graph = dependency_graph_from_payload(payload["m5"]["graph"])
    artifacts = tuple(
        integration_artifact_definition_from_payload(item)
        for item in payload["artifacts"]
    )
    baseline_statuses = {
        "portfolio_risk": _baseline_status(risk.status),
        "position_guidance": _baseline_status(guidance.status),
    }
    baseline_statuses.update(
        {
            item.artifact_id: STATUS_READY
            for item in artifacts
            if item.artifact_id not in baseline_statuses
        }
    )
    result = build_m4_m5_integration(
        receipt=m5_receipt,
        graph=graph,
        artifacts=artifacts,
        baseline_statuses=baseline_statuses,
        generated_at=_datetime(payload["generated_at"], "generated_at"),
    )
    return result, risk, guidance, dividend, {
        "risk": risk_receipt,
        "guidance_income": guidance_receipt,
        "m5_watermark_id": watermark.watermark_id,
    }


def main() -> int:
    args = parse_args()
    payload, input_receipts = load_input(args.input.resolve())
    result, risk, guidance, dividend, model_receipts = build_models(
        payload,
        base_dir=ROOT,
    )
    output = args.output.resolve()
    workbook_result = write_m4_m5_integration_workbook(
        result,
        risk,
        guidance,
        dividend,
        output=output,
        root=output.parent,
        security_names=payload.get("security_names"),
    )
    manifest = {
        **workbook_result,
        "schema_version": SCHEMA_VERSION,
        "result_id": result.result_id,
        "generated_at": result.generated_at.isoformat(),
        "artifact_statuses": [artifact.as_policy() for artifact in result.artifacts],
        "input": input_receipts,
        "m5": {
            "run_id": result.receipt.run_id,
            "receipt_id": result.receipt.receipt_id,
            "health_status": result.receipt.health_status,
            "review_due": list(result.receipt.review_due),
        },
    }
    output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
