"""Acquire a bounded official scan supplement for a registered research package."""
import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from value_investment_agent.application.product.incremental_validity import (  # noqa: E402
    collect_registered_validity_scan,
    register_incremental_validity_binding,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--review-cutoff", type=date.fromisoformat, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--register", action="store_true", help="Explicitly register the verified supplement; grants no approval.")
    args = parser.parse_args()
    result = collect_registered_validity_scan(root=ROOT, symbol=args.symbol,
        review_cutoff=args.review_cutoff, output_dir=args.output_dir)
    if args.register:
        result["registration"] = register_incremental_validity_binding(ROOT, args.symbol,
            result["binding_ref"], args.review_cutoff, datetime.now(timezone.utc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
