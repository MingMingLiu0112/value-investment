"""Thin CLI: extract PIT facts from the remote read-only store into local files.

The remote host is storage-only and memory-constrained, so this script only
moves bytes off the server; every computation happens locally afterwards.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from value_investment_agent.infrastructure.data.pit_extract import (  # noqa: E402
    QUALITY_FIELDS,
    extract_disclosure_dates,
    extract_instruments,
    extract_quality_facts,
    write_receipt,
)
from value_investment_agent.settings import get_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="runtime/p0/db")
    parser.add_argument("--statuses", default="verified",
                        help="comma-separated validation_status filter")
    parser.add_argument("--skip-prices-note", action="store_true",
                        help="print the note that prices are not in this store")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    statuses = tuple(s.strip() for s in args.statuses.split(",") if s.strip())

    results = [
        extract_quality_facts(settings.database_url, out_dir / "quality_facts.csv",
                              fields=QUALITY_FIELDS, statuses=statuses),
        extract_disclosure_dates(settings.database_url, out_dir / "disclosure_dates.csv"),
        extract_instruments(settings.database_url, out_dir / "instruments.csv"),
    ]
    write_receipt(results, out_dir / "extract_receipt.json")

    for item in results:
        print(f"{item.table:22s} {item.rows:>8,} 行 -> {item.path}")
    if args.skip_prices_note:
        print("note: this store has no daily bar table; prices come from a local fetch")
    print(f"\nreceipt -> {out_dir / 'extract_receipt.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
