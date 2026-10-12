"""Build a hash-bound, non-admitted M2 data-check queue."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product.common import require_inside, write_new_json
from value_investment_agent.application.research.value_research_queue import build_value_research_queue


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--budget", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--previous-sha256")
    args = parser.parse_args()
    if (args.previous is None) != (args.previous_sha256 is None):
        parser.error("previous queue requires path and hash")
    output = require_inside(ROOT / "runtime", ROOT / args.output, "value research queue")
    queue = build_value_research_queue(root=ROOT, report_path=ROOT / args.report,
        report_sha256=args.report_sha256, receipt_path=ROOT / args.receipt,
        receipt_sha256=args.receipt_sha256, budget=args.budget,
        previous_path=ROOT / args.previous if args.previous else None,
        previous_sha256=args.previous_sha256)
    write_new_json(output, queue)
    print(json.dumps({key: value for key, value in queue.items() if key != "entries"},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
