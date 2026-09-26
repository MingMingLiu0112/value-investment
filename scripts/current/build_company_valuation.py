"""Build one symbol-specific research valuation result through the shared model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product import build_company_valuation_for_symbol  # noqa: E402


def _inside_root(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--case-path", required=True, type=Path)
    parser.add_argument("--facts-path", required=True, type=Path)
    parser.add_argument("--model", required=True, choices=("fcff",))
    parser.add_argument("--profile-id")
    parser.add_argument("--applicability-path", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = build_company_valuation_for_symbol(
        root=ROOT,
        symbol=args.symbol,
        case_path=_inside_root(args.case_path),
        facts_path=_inside_root(args.facts_path),
        model=args.model,
        profile_id=args.profile_id,
        applicability_path=(
            _inside_root(args.applicability_path)
            if args.applicability_path is not None else None
        ),
        output_path=_inside_root(args.output),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
