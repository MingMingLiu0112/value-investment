"""Audit incremental validity for current quote-pointer research bindings."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from value_investment_agent.application.product.common import sha256_file  # noqa: E402
from value_investment_agent.application.product.research_validity_review import (  # noqa: E402
    review_registered_research_validity,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--review-cutoff", type=date.fromisoformat, required=True)
    parser.add_argument("--symbol", action="append", help="Repeat to select symbols; default: all registered.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--incremental-binding", nargs=2, action="append", metavar=("PATH", "SHA256"),
                        help="Explicit immutable supplement; repeat for different symbols.")
    args = parser.parse_args()
    result = review_registered_research_validity(root=ROOT, review_cutoff=args.review_cutoff,
        today=datetime.now(timezone.utc), output_path=args.output, symbols=args.symbol,
        incremental_bindings=[{"path": path, "sha256": digest}
                              for path, digest in args.incremental_binding or []])
    print(json.dumps({"artifact": args.output.as_posix(),
        "artifact_sha256": sha256_file(ROOT / args.output), "action": "no_order",
        "reviews": [{"symbol": row["symbol"], "status": row["status"],
                     "model_validity_status": row["model_validity_status"],
                     "reason": row.get("reason")} for row in result["reviews"]]},
        ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
