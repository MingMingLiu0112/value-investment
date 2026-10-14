"""Refresh at most five current price observations; never authorize orders."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.hotspot.current_refresh import current_watch_binding, refresh_current_price_conditions


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--watch-source", type=Path)
    parser.add_argument("--watch-source-sha256")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        if (args.watch_source is None) != (args.watch_source_sha256 is None):
            raise ValueError("watch-source and watch-source-sha256 must be supplied together")
        binding = (current_watch_binding(args.root) if args.watch_source is None else
                   dict(path=args.watch_source, sha256=args.watch_source_sha256))
        result = refresh_current_price_conditions(root=args.root, watch_source_path=Path(binding["path"]),
            watch_source_sha256=binding["sha256"], limit=args.limit)
    except Exception as error:
        result = dict(status="BLOCKED", items=[], failures=[dict(reason=type(error).__name__ + ":" + str(error))],
                      action="no_order")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "WRITTEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
