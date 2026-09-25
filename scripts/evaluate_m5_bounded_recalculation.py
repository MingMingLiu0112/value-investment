"""Persist a write-once fail-closed ACTUAL bounded recalculation gate result."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m5_bounded_recalculation_result import evaluate_bounded_recalculation  # noqa: E402
from value_investment_agent.m5_event_dependencies import dependency_graph_from_payload  # noqa: E402
from value_investment_agent.m5_event_run import m5_event_run_receipt_from_payload  # noqa: E402
from value_investment_agent.m5_recalculation_plan import bounded_recalculation_plan_from_payload  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("receipt", "graph", "plan", "facts", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Bounded recalculation result is write-once")
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    payload = evaluate_bounded_recalculation(
        receipt=m5_event_run_receipt_from_payload(load(args.receipt)["receipt"]),
        graph=dependency_graph_from_payload(load(args.graph)["graph"]),
        plan=bounded_recalculation_plan_from_payload(load(args.plan)),
        facts_artifact=load(args.facts), evaluated_at=datetime.now(timezone.utc),
        facts_source_sha256=hashlib.sha256(args.facts.read_bytes()).hexdigest(),
    )
    payload["input_file_sha256"] = {
        name: hashlib.sha256(getattr(args, name).read_bytes()).hexdigest()
        for name in ("receipt", "graph", "plan", "facts")
    }
    # The file manifest sits outside the canonical result hash.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "outcomes": [(item["event_id"], item["status"]) for item in payload["outcomes"]],
                      "action": "no_order"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
