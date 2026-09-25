"""Build a hash-bound M7 read model from reviewed ACTUAL M5 artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m5_actual_read_model import build_actual_event_read_model  # noqa: E402
from value_investment_agent.m5_event_dependencies import dependency_graph_from_payload  # noqa: E402
from value_investment_agent.m5_event_run import m5_event_run_receipt_from_payload  # noqa: E402
from value_investment_agent.m5_recalculation_plan import bounded_recalculation_plan_from_payload  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("queue", "reviews", "review-manifest", "receipt", "graph", "plan", "facts", "outcome", "output"):
        parser.add_argument("--" + name, required=name != "facts", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("M5 actual event read model output is write-once")
    paths = {name: getattr(args, name.replace("-", "_")).resolve()
             for name in ("queue", "reviews", "review-manifest", "receipt", "graph", "plan", "outcome")}
    data = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()}
    manifest = data["review-manifest"]
    if (manifest.get("schema_version") != "m5-delegated-review-application-v1"
        or manifest.get("review_provenance") != "USER_CONFIRMED_DELEGATED_REVIEW"
        or manifest.get("action") != "no_order"
        or manifest["files"]["reviews.json"]["sha256"] != hashlib.sha256(paths["reviews"].read_bytes()).hexdigest()
        or manifest["queue"]["sha256"] != hashlib.sha256(paths["queue"].read_bytes()).hexdigest()):
        raise ValueError("Human review manifest does not bind the review and queue bytes")
    graph = dependency_graph_from_payload(data["graph"]["graph"])
    facts = json.loads(args.facts.read_text(encoding="utf-8")) if args.facts else None
    model = build_actual_event_read_model(
        queue=data["queue"], reviews=data["reviews"],
        receipt=m5_event_run_receipt_from_payload(data["receipt"]["receipt"]),
        graph=graph, plan=bounded_recalculation_plan_from_payload(data["plan"]),
        facts_artifact=facts, outcome_receipt=data["outcome"],
        facts_source_sha256=hashlib.sha256(args.facts.read_bytes()).hexdigest() if args.facts else None,
    )
    model["input_sha256"] = {
        name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()
    }
    if args.facts:
        model["input_sha256"]["facts"] = hashlib.sha256(args.facts.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "reviewed_count": model["reviewed_count"], "action": "no_order"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
