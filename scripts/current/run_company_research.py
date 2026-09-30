"""Run shared company research for one explicit symbol."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product import run_company_research_for_symbol  # noqa: E402
from value_investment_agent.application.product.common import (  # noqa: E402
    load_json_object,
    sha256_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--schedule-request", type=Path,
        help="Hash-bound JSON scope request required to reopen an Evidence Stop.",
    )
    args = parser.parse_args()
    package = None if args.package is None else (
        args.package if args.package.is_absolute() else ROOT / args.package
    )
    output = None if args.output is None else (
        args.output if args.output.is_absolute() else ROOT / args.output
    )
    schedule_request = None
    schedule_request_sha256 = None
    if args.schedule_request is not None:
        request_path = args.schedule_request
        if not request_path.is_absolute():
            request_path = ROOT / request_path
        request_path = request_path.resolve()
        if not request_path.is_relative_to(ROOT.resolve()):
            raise ValueError("schedule request must remain under the project root")
        schedule_request = load_json_object(request_path, "schedule request")
        schedule_request_sha256 = sha256_file(request_path)
    result = run_company_research_for_symbol(
        root=ROOT,
        symbol=args.symbol,
        package_path=package,
        output_path=output,
        schedule_request=schedule_request,
        schedule_request_sha256=schedule_request_sha256,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
