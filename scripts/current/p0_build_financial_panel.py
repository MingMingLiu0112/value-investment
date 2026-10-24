"""Thin CLI: materialise a point-in-time financial panel for P0 research.

All PIT and universe rules live in `domain/pit`; all fetching lives in
`infrastructure/data/public_financial_panel`. This script only parses args,
invokes the adapter, writes the CSV receipt and returns an exit code.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.infrastructure.data import public_financial_panel as panel  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2019)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--annual-only", action="store_true",
                        help="keep 12-31 periods only (matches the existing scorer)")
    args = parser.parse_args()

    result = panel.build(args.start_year, args.end_year, annual_only=args.annual_only,
                         progress=lambda msg: print(msg))
    panel.write_csv(result, args.out)

    summary = result.as_dict()
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                encoding="utf-8")

    print(f"\nwritten -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
