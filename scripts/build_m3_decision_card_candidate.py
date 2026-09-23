"""Build a standalone M3 decision-card Excel candidate from frozen M1 evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from value_investment_agent.m1_sample_preregistration import (
    load_m1_sample_preregistration,
)
from value_investment_agent.m3_decision_application import (
    build_nonpersonal_decision_card_collection,
    load_integrated_runs,
)
from value_investment_agent.m3_decision_card_workbook import (
    write_decision_card_workbook,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT
    / "runtime"
    / "m1-post-review-20260923T114228Z"
    / "integrated-runs.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / f"A股价值投资_M3决策卡候选_{datetime.now().astimezone():%Y%m%d}.xlsx",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    integrated_runs, input_receipt = load_integrated_runs(ROOT, args.input)
    generated_at = datetime.fromtimestamp(
        args.input.resolve().stat().st_mtime,
        tz=timezone.utc,
    )
    names = {
        entry.symbol: entry.name
        for entry in load_m1_sample_preregistration().companies
    }
    source_run_id = args.input.resolve().parent.name
    collection = build_nonpersonal_decision_card_collection(
        integrated_runs,
        generated_at=generated_at,
        source_run_id=source_run_id,
    )
    result = write_decision_card_workbook(
        collection,
        output=args.output,
        root=args.output.resolve().parent,
        security_names=names,
    )
    manifest = {
        **result,
        "schema_version": collection.schema_version,
        "source_run_id": source_run_id,
        "generated_at": generated_at.isoformat(),
        "input": input_receipt,
        "input_failure_count": len(collection.input_failures),
        "input_failures": [failure.as_policy() for failure in collection.input_failures],
    }
    args.output.resolve().with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
