"""Screen dated daily market candidates and refresh bounded price observations."""

import argparse
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.hotspot.current_refresh import refresh_current_price_conditions
from value_investment_agent.application.hotspot.daily_selection import collect_daily_candidates
from value_investment_agent.application.product.daily_refresh import refresh_readiness


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--watch-source", type=Path)
    parser.add_argument("--watch-source-sha256")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--candidate-pool-limit", type=int)
    parser.add_argument("--check-reuse", action="store_true")
    parser.add_argument("--symbols", default="600887")
    args = parser.parse_args(argv)
    if args.check_reuse:
        print(json.dumps(refresh_readiness(args.root, now=datetime.now(timezone.utc),
            symbols=args.symbols.split(",")), ensure_ascii=False))
        return 0
    try:
        if (args.watch_source is None) != (args.watch_source_sha256 is None):
            raise ValueError("watch-source and watch-source-sha256 must be supplied together")
        binding = (collect_daily_candidates(
            root=args.root, limit=args.limit,
            candidate_pool_limit=args.candidate_pool_limit,
        ) if args.watch_source is None else
                   dict(path=args.watch_source, sha256=args.watch_source_sha256))
        result = refresh_current_price_conditions(root=args.root, watch_source_path=Path(binding["path"]),
            watch_source_sha256=binding["sha256"], limit=args.limit,
            candidate_pool_limit=args.candidate_pool_limit)
    except Exception as error:
        result = dict(status="BLOCKED", items=[], failures=[dict(reason=type(error).__name__ + ":" + str(error))],
                      action="no_order")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return (3 if result.get("failures") else 0) if result["status"] == "WRITTEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
