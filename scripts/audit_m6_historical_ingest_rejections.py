#!/usr/bin/env python3
"""Read-only M6 view of historical rejected M5 ingest verdicts.

This command does not instantiate a writable M5 store, connect to PostgreSQL,
change a scheduler or notification target, publish a workbook or create an
order. It fails closed when durable receipt evidence is missing or inconsistent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m6_historical_ingest_rejections import (  # noqa: E402
    M6HistoricalIngestRejectionError,
    build_historical_ingest_rejection_view_from_paths,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-key", required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument("--json-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        view = build_historical_ingest_rejection_view_from_paths(
            state_key=args.state_key,
            state_root=args.state_root.resolve(),
            receipt_root=args.receipt_root.resolve(),
        )
    except (M6HistoricalIngestRejectionError, OSError, ValueError) as error:
        print(f"integrity failure: {error}", file=sys.stderr)
        return 2

    if args.json_only:
        print(json.dumps(view, ensure_ascii=False, indent=2))
        return 0
    print(f"status: {view['status']}")
    print(f"state_key: {view['state_key']}")
    print(f"historical_rejection_count: {view['historical_rejection_count']}")
    print(f"current_state_revision: {view['current_state']['revision']}")
    print(
        "latest_receipt_health_status: "
        f"{view['current_state']['latest_receipt_health_status']}"
    )
    print(f"integrity: {view['integrity']['status']}")
    print(f"evidence_class: {view['boundary']['evidence_class']}")
    print("action: no_order")
    for item in view["historical_rejections"]:
        print(
            "  - "
            f"{item['generated_at']} {item['status']} "
            f"batch={item['batch_id']} receipt={item['receipt_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
