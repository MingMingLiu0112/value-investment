"""Build a symbol-neutral current-workbench request from shared research output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product import build_current_workbench_for_symbol  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    package = None if args.package is None else (
        args.package if args.package.is_absolute() else ROOT / args.package
    )
    output = args.output if args.output.is_absolute() else ROOT / args.output
    result = build_current_workbench_for_symbol(
        root=ROOT,
        symbol=args.symbol,
        package_path=package,
        output_path=output,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
