"""Replay one archived M1 quote-session symbol as a typed QuoteSnapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.quote_session_conversion import (
    quote_snapshot_from_bundle_file,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--ref-id", required=True)
    parser.add_argument("--sha256")
    args = parser.parse_args(argv)
    snapshot = quote_snapshot_from_bundle_file(
        Path(args.bundle),
        ROOT,
        symbol=args.symbol,
        ref_id=args.ref_id,
        expected_sha256=args.sha256,
    )
    print(snapshot.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
