"""Record a user-supplied negative scenario review without changing M5 state."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m5_actual_read_model import build_actual_event_read_model  # noqa: E402
from value_investment_agent.m5_event_dependencies import dependency_graph_from_payload  # noqa: E402
from value_investment_agent.m5_event_run import m5_event_run_receipt_from_payload  # noqa: E402
from value_investment_agent.m5_recalculation_plan import bounded_recalculation_plan_from_payload, _sha  # noqa: E402
from value_investment_agent.m5_scenario_research_review import build_need_more_evidence_review  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("queue", "reviews", "receipt", "graph", "plan", "facts", "outcome",
                 "pending-input", "review-package", "review-source", "output", "read-model-output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    paths = {name: getattr(args, name.replace("-", "_")).resolve() for name in
             ("queue", "reviews", "receipt", "graph", "plan", "facts", "outcome",
              "pending-input", "review-package", "review-source")}
    output = args.output.resolve()
    model_output = args.read_model_output.resolve()
    if output == model_output or output.exists() or model_output.exists():
        raise ValueError("Review receipt and read model outputs must be distinct and write-once")
    load = lambda name: json.loads(paths[name].read_text(encoding="utf-8"))
    queue, reviews, outcome, facts = (load(name) for name in ("queue", "reviews", "outcome", "facts"))
    decisions = [item for review in reviews for item in review["decisions"]]
    receipt = m5_event_run_receipt_from_payload(load("receipt")["receipt"])
    graph = dependency_graph_from_payload(load("graph")["graph"])
    plan = bounded_recalculation_plan_from_payload(load("plan"))
    source_bytes = paths["review-source"].read_bytes()
    package_bytes = paths["review-package"].read_bytes()
    pending_bytes = paths["pending-input"].read_bytes()
    review = build_need_more_evidence_review(
        source_bytes=source_bytes, review_package_bytes=package_bytes,
        pending_input_bytes=pending_bytes, receipt=receipt,
        decisions=decisions, graph_sha256=_sha(graph.as_policy()),
        facts_payload_sha256=facts["payload_sha256"],
        facts_file_sha256=hashlib.sha256(paths["facts"].read_bytes()).hexdigest(),
        bounded_result_sha256=outcome["result_sha256"],
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    model = build_actual_event_read_model(
        queue=queue, reviews=reviews, receipt=receipt, graph=graph, plan=plan,
        facts_artifact=facts, outcome_receipt=outcome,
        facts_source_sha256=review["facts_file_sha256"], scenario_review=review,
        scenario_review_source_bytes=source_bytes,
        scenario_review_package_bytes=package_bytes,
        scenario_review_pending_input_bytes=pending_bytes,
    )
    model["input_sha256"] = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for name, path in paths.items()}
    model["scenario_review_file_sha256"] = hashlib.sha256(
        (json.dumps(review, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    ).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    model_output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
    with model_output.open("x", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(model, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"review": str(output), "review_sha256": review["review_sha256"],
                      "read_model": str(model_output), "action": "no_order"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
