"""Run the frozen three-company research replay and emit an audit receipt.

The command is offline, deterministic for a fixed ``--run-id``, and never
connects to a production database or produces an execution instruction.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
)
from value_investment_agent.research_e2e_replay import run_three_company_replay


ROOT = Path(__file__).resolve().parents[1]


def _default_run_id() -> str:
    return "three-company-replay-" + datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay the frozen fixed sample through the shared research pipeline"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root containing tracked config and frozen runtime pointers",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional fixed-sample manifest; defaults to ROOT/config/fixed-sample-manifest.json",
    )
    parser.add_argument("--run-id", default=_default_run_id())
    parser.add_argument(
        "--receipt",
        type=Path,
        help="Receipt output path; defaults to runtime/three-company-e2e-replay-RUN_ID.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = args.root.resolve()
    receipt = args.receipt
    if receipt is None:
        receipt = root / "runtime" / f"three-company-e2e-replay-{args.run_id}.json"

    result = run_three_company_replay(
        InMemoryResearchArtifactRepository(),
        root=root,
        manifest_path=args.manifest,
        run_id=args.run_id,
    )
    policy = result.as_policy()
    payload = json.dumps(policy, ensure_ascii=False, sort_keys=True, indent=2)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(payload + "\n", encoding="utf-8")
    print(json.dumps(policy, ensure_ascii=False, sort_keys=True, indent=2))
    print(
        f"receipt={receipt.resolve()} all_semantics_matched="
        f"{result.all_semantics_matched} action={result.action}",
        file=sys.stderr,
    )
    return 0 if result.all_semantics_matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
