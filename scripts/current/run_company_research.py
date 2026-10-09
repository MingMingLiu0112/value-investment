"""Run shared company research for one explicit symbol."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product import run_company_research_for_symbol  # noqa: E402
from value_investment_agent.domain.decision.decision_recommendation import (  # noqa: E402
    DECISION_RECOMMENDATION_SCHEMA, DECISION_RECOMMENDATION_V3_SCHEMA,
)
from value_investment_agent.application.product.existing_valuation import read_existing_research_result  # noqa: E402
from value_investment_agent.application.product.common import load_json_object, sha256_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--existing-manifest", type=Path, help="Read a pinned existing result only; do not rerun research.")
    parser.add_argument("--existing-manifest-sha256")
    parser.add_argument("--arithmetic-input", type=Path)
    parser.add_argument("--arithmetic-input-sha256")
    parser.add_argument("--quote", type=Path)
    parser.add_argument("--quote-sha256")
    parser.add_argument("--event", type=Path)
    parser.add_argument("--event-sha256")
    parser.add_argument("--research-reviews", type=Path)
    parser.add_argument("--research-reviews-sha256")
    parser.add_argument(
        "--recommendation-schema-version",
        choices=(DECISION_RECOMMENDATION_SCHEMA, DECISION_RECOMMENDATION_V3_SCHEMA),
    )
    parser.add_argument("--schedule-request", type=Path, help="Hash-bound JSON scope request required to reopen an Evidence Stop.")
    args = parser.parse_args()
    resolve = lambda value: None if value is None else (value if value.is_absolute() else ROOT / value)
    package = resolve(args.package)
    output = resolve(args.output)
    if args.existing_manifest is not None or args.existing_manifest_sha256 is not None:
        market_args = (args.quote, args.quote_sha256, args.event, args.event_sha256,
                       args.research_reviews, args.research_reviews_sha256)
        if args.existing_manifest is None or args.existing_manifest_sha256 is None:
            parser.error("existing mode requires manifest and hash")
        if args.package is not None or args.schedule_request is not None or args.recommendation_schema_version is not None or any(
            value is not None for value in market_args
        ):
            parser.error("existing mode excludes package/schedule/market/review inputs")
        manifest_path = (args.existing_manifest if args.existing_manifest.is_absolute()
                         else ROOT / args.existing_manifest)
        arithmetic_path = (None if args.arithmetic_input is None else
                           resolve(args.arithmetic_input))
        result = read_existing_research_result(
            root=ROOT, symbol=args.symbol, manifest_path=manifest_path,
            manifest_sha256=args.existing_manifest_sha256, output_path=output,
            arithmetic_input_path=arithmetic_path,
            arithmetic_input_sha256=args.arithmetic_input_sha256,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.arithmetic_input is not None or args.arithmetic_input_sha256 is not None:
        parser.error("arithmetic input requires existing-result read mode")
    schedule_request = schedule_request_sha256 = None
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
        root=ROOT, symbol=args.symbol, package_path=package, output_path=output,
        schedule_request=schedule_request, schedule_request_sha256=schedule_request_sha256,
        quote_path=resolve(args.quote), quote_sha256=args.quote_sha256,
        event_path=resolve(args.event), event_sha256=args.event_sha256,
        reviews_path=resolve(args.research_reviews), reviews_sha256=args.research_reviews_sha256,
        recommendation_schema_version=args.recommendation_schema_version,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
