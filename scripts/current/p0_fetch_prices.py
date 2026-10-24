"""Thin CLI: fetch a wide public daily-bar matrix for P0 research.

All fetching, adjustment policy and concurrency live in
`infrastructure/data/public_price_bars`; the universe boundary lives in
`domain/pit/universe`. This script only resolves the symbol list from a CSV
column, invokes the adapter, writes the npz and returns an exit code.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.infrastructure.data import public_price_bars as bars  # noqa: E402


def _codes(args) -> list[str]:
    frame = pd.read_csv(args.symbols_from, dtype={"symbol": str}, usecols=["symbol"])
    codes = frame["symbol"].dropna().astype(str).str.zfill(6).unique().tolist()
    return codes[: args.limit] if args.limit else codes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols-from", type=Path, required=True,
                        help="CSV containing a `symbol` column")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--start", default="20190101")
    parser.add_argument("--end", default="20261231")
    parser.add_argument("--workers", type=int, default=8,
                        help="processes, not threads: py_mini_racer is not thread-safe")
    parser.add_argument("--limit", type=int, default=0, help="0 = no limit")
    args = parser.parse_args()

    codes = _codes(args)
    print(f"universe {len(codes)} symbols from {args.symbols_from}")

    result = bars.fetch_matrix(codes, args.start, args.end, workers=args.workers,
                               progress=lambda msg: print(msg))
    bars.save_npz(result, args.out)

    summary = result.as_dict()
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    if result.failed:
        failed_path = args.out.with_name(args.out.stem + "_failed.txt")
        failed_path.write_text("\n".join(sorted(result.failed)), encoding="utf-8")
        print(f"failed symbols -> {failed_path}")

    print(f"\nwritten -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
