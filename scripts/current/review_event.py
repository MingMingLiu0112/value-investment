"""Review one symbol's disclosure queue without applying events or notifying."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product import review_event_for_symbol  # noqa: E402


def _inside_root(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--intake", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--archive-root", type=Path)
    parser.add_argument(
        "--review-provenance",
        required=True,
        choices=("USER_CONFIRMED_DELEGATED_REVIEW",),
        help=(
            "explicit, self-asserted review provenance claim; the run still "
            "requires a signed approval receipt before any event is applied"
        ),
    )
    args = parser.parse_args()
    result = review_event_for_symbol(
        root=ROOT,
        symbol=args.symbol,
        queue_path=_inside_root(args.queue),
        intake_path=_inside_root(args.intake),
        runtime_root=_inside_root(args.runtime_root),
        archive_root=(
            _inside_root(args.archive_root) if args.archive_root is not None else None
        ),
        review_provenance=args.review_provenance,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
