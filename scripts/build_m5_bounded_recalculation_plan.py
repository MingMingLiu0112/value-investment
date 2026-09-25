"""Write a read-only M5 bounded recalculation plan from frozen inputs."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m5_event_dependencies import dependency_graph_from_payload  # noqa: E402
from value_investment_agent.m5_event_run import m5_event_run_receipt_from_payload  # noqa: E402
from value_investment_agent.m5_recalculation_plan import build_bounded_recalculation_plan  # noqa: E402


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--graph-receipt", required=True, type=Path)
    parser.add_argument("--generated-at", required=True, type=datetime.fromisoformat)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.generated_at.tzinfo is None:
        raise ValueError("--generated-at must include a timezone")
    receipt_path = args.receipt.resolve()
    graph_path = args.graph_receipt.resolve()
    output = args.output.resolve()
    if output.exists() or not receipt_path.is_file() or not graph_path.is_file():
        raise ValueError("output must be new and frozen inputs must exist")
    receipt_artifact = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt = m5_event_run_receipt_from_payload(receipt_artifact["receipt"])
    graph_artifact = json.loads(graph_path.read_text(encoding="utf-8"))
    graph = dependency_graph_from_payload(graph_artifact["graph"])
    plan = build_bounded_recalculation_plan(
        receipt=receipt, graph=graph, generated_at=args.generated_at,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan.as_policy(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "receipt": {"path": str(receipt_path), "sha256": _digest(receipt_path)},
        "graph_receipt": {"path": str(graph_path), "sha256": _digest(graph_path)},
        "plan": {"path": str(output), "sha256": _digest(output)},
        "action": "no_order",
    }
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
