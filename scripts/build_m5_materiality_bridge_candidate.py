"""Build a standalone simulated M5 materiality-bridge Excel candidate."""
from __future__ import annotations

import argparse
from datetime import datetime, time, timezone, timedelta
import hashlib
import json
from pathlib import Path

from value_investment_agent.event_materiality import (
    event_materiality_review_from_payload,
)
from value_investment_agent.investment_decision import ACTION_NO_ORDER
from value_investment_agent.m5_event_core import NAMESPACE_SIMULATED
from value_investment_agent.m5_event_dependencies import (
    KIND_CURRENT_STATUS,
    KIND_DECISION_REVIEW,
    KIND_DISTRIBUTION_HISTORY,
    KIND_DIVIDEND_SUSTAINABILITY,
    KIND_FACTS,
    KIND_MODEL_VALIDITY,
    KIND_PORTFOLIO_RISK,
    KIND_THESIS,
    KIND_VALUATION_INPUTS,
    DependencyGraph,
    DependencyNode,
)
from value_investment_agent.m5_event_run import run_event_batch
from value_investment_agent.m5_event_watermark import (
    SOURCE_HEALTHY,
    WATERMARK_COVERAGE_COMPLETE,
    ScanWatermark,
)
from value_investment_agent.m5_materiality_bridge import (
    MATERIALITY_BRIDGE_SCHEMA,
    build_materiality_bridge_batch,
)
from value_investment_agent.m5_materiality_workbook import (
    write_m5_materiality_workbook,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "tests" / "fixtures" / "m5_materiality_bridge_demo.json"
SCHEMA_VERSION = MATERIALITY_BRIDGE_SCHEMA
TZ = timezone(timedelta(hours=8))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "A股价值投资_M5材料性接入候选_20260924.xlsx",
    )
    return parser.parse_args()


def load_input(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Materiality bridge input must be a JSON object")
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("Materiality bridge input must remain no_order")
    review = event_materiality_review_from_payload(payload)
    if review.symbol == "SYSTEM":
        raise ValueError("Public materiality candidate must use a security")
    return review, {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _graph(symbol: str) -> DependencyGraph:
    def node(
        node_id: str,
        kind: str,
        inputs: tuple[str, ...] = (),
    ) -> DependencyNode:
        return DependencyNode(
            node_id=f"{node_id}-{symbol}",
            kind=kind,
            symbol=symbol,
            inputs=tuple(f"{item}-{symbol}" for item in inputs),
            version="m5-materiality-demo-v1",
            evidence_refs=({"id": f"{node_id}-evidence"},),
        )

    return DependencyGraph(
        (
            node("facts", KIND_FACTS),
            node("valuation-inputs", KIND_VALUATION_INPUTS, ("facts",)),
            node("distribution-history", KIND_DISTRIBUTION_HISTORY, ("facts",)),
            node("dividend-sustainability", KIND_DIVIDEND_SUSTAINABILITY, ("distribution-history",)),
            node("model-validity", KIND_MODEL_VALIDITY, ("facts", "valuation-inputs")),
            node("research-thesis", KIND_THESIS, ("facts", "valuation-inputs")),
            node("decision-review", KIND_DECISION_REVIEW, ("model-validity", "research-thesis")),
            node("current-status", KIND_CURRENT_STATUS, ("decision-review",)),
            node("portfolio-risk", KIND_PORTFOLIO_RISK, ("facts",)),
        )
    )


def _watermark(review) -> ScanWatermark:
    retrieved_at = datetime.combine(
        review.scan_to,
        time(16, 0, tzinfo=TZ),
    )
    return ScanWatermark(
        watermark_id=f"{review.review_id}-watermark",
        scope=review.symbol,
        source="simulated-cninfo",
        coverage_through=retrieved_at,
        retrieved_at=retrieved_at,
        parser_version="m5-materiality-demo-v1",
        coverage_status=WATERMARK_COVERAGE_COMPLETE,
        source_health=SOURCE_HEALTHY,
        evidence_refs=({"id": "simulated-scan"},),
    )


def build_models(input_path: Path):
    review, input_receipt = load_input(input_path.resolve())
    batch = build_materiality_bridge_batch(
        review,
        namespace=NAMESPACE_SIMULATED,
    )
    watermark = _watermark(review)
    receipt = run_event_batch(
        events=batch.events,
        observed_times=batch.observed_times,
        watermark=watermark,
        graph=_graph(review.symbol),
        run_id=f"materiality-{review.review_id}",
        generated_at=watermark.retrieved_at,
        namespace=NAMESPACE_SIMULATED,
        direct_kinds_by_source_event_id=batch.direct_kinds_by_source_event_id,
    )
    return batch, receipt, watermark


def main() -> int:
    args = parse_args()
    _, input_receipt = load_input(args.input)
    batch, receipt, watermark = build_models(args.input)
    result = write_m5_materiality_workbook(
        batch,
        receipt,
        watermark,
        output=args.output,
        root=args.output.resolve().parent,
        security_names={"600887": "模拟公司"},
    )
    manifest = {
        **result,
        "schema_version": SCHEMA_VERSION,
        "run_id": receipt.run_id,
        "generated_at": receipt.generated_at.isoformat(),
        "input": input_receipt,
        "health_status": receipt.health_status,
        "silent_ok": receipt.silent_ok,
        "review_due": list(receipt.review_due),
        "direct_kinds_by_source_event_id": {
            key: list(value)
            for key, value in batch.direct_kinds_by_source_event_id.items()
        },
    }
    manifest_path = args.output.resolve().with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
