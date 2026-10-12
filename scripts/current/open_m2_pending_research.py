"""Open one bound M2 lead as a blocked official-source research case."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product.m2_candidate_intake import open_pending_m2_research


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = open_pending_m2_research(root=ROOT, queue_path=ROOT / args.queue,
        queue_sha256=args.sha256, symbol=args.symbol, profile_id=args.profile_id,
        output_dir=ROOT / args.output_dir)
    print(json.dumps({key: value for key, value in result.items() if key != "research_case"},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
