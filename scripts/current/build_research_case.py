"""Build one validated ResearchCase from a symbol-neutral public evidence file."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product import build_research_case_for_symbol  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "runtime" / "excel-mvp-research-cases" / "evidence.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.source if args.source.is_absolute() else ROOT / args.source
    output = None if args.output is None else (
        args.output if args.output.is_absolute() else ROOT / args.output
    )
    result = build_research_case_for_symbol(
        root=ROOT,
        symbol=args.symbol,
        source_path=source,
        output_path=output,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
