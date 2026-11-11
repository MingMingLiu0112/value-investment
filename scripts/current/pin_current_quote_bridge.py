"""Register one archived dual-source close for the shared price-bridge entry."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product.quote_bridge import (  # noqa: E402
    execute_quote_bridge_for_symbol,
    pin_quote_bridge_for_symbol,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--quote-bundle", required=True,
                        help="Archived dual-source quote bundle under runtime/.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--research-package",
                        help="Registered research package the quote is pinned against.")
    scope.add_argument("--observation-only", action="store_true",
                       help="Only display a verified close; no research or price admission.")
    parser.add_argument("--registered-at", help="Explicit registration timestamp for replay.")
    args = parser.parse_args()
    pinned = pin_quote_bridge_for_symbol(
        ROOT, args.symbol, args.quote_bundle, args.research_package,
        registered_at=args.registered_at)
    verdict = execute_quote_bridge_for_symbol(
        ROOT, args.symbol, today=datetime.now(timezone.utc))
    print(json.dumps({"pinned": pinned, "verdict": verdict, "action": "no_order"},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
