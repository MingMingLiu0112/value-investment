"""Export a hash-pinned M5 dependency graph for one runtime research case."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m5_research_artifact_graph import build_research_artifact_dependency_graph  # noqa: E402
from value_investment_agent.research_runtime_import import build_runtime_candidates  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Dependency graph receipt output already exists")
    candidates, missing = build_runtime_candidates(ROOT, run_id=args.run_id, symbols=(args.symbol,))
    if missing:
        raise ValueError(f"Cannot build dependency graph with missing artifacts: {missing}")
    graph = build_research_artifact_dependency_graph(candidates, symbol=args.symbol)
    payload = {
        "schema_version": "m5-research-artifact-dependency-graph-v1",
        "symbol": args.symbol,
        "run_id": args.run_id,
        "graph": graph.as_policy(),
        "input_artifacts": [
            {
                "artifact_type": candidate.artifact_type,
                "source_path": str(candidate.source_path),
                "source_sha256": candidate.source_sha256,
            }
            for candidate in candidates
            if candidate.symbol == args.symbol
        ],
        "action": "no_order",
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(encoded, encoding="utf-8")
    print(json.dumps({"path": str(output), "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(), "node_count": len(graph.nodes()), "action": "no_order"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
