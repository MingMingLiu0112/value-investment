"""Run shared company research for one explicit symbol."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product.company_research import (  # noqa: E402
    load_schedule_request, run_company_research_for_symbol,
)
from value_investment_agent.domain.decision.decision_recommendation import (  # noqa: E402
    DECISION_RECOMMENDATION_SCHEMA, DECISION_RECOMMENDATION_V3_SCHEMA,
)
from value_investment_agent.application.product.existing_valuation import read_existing_research_result  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    for flag in ('--package', '--output', '--arithmetic-input', '--quote', '--event', '--research-reviews',
                 '--pending-review-candidate', '--signed-review-response', '--review-trust-root', '--previous-review-response'):
        parser.add_argument(flag, type=Path)
    parser.add_argument("--existing-manifest", type=Path, help="Read a pinned existing result only; do not rerun research.")
    for flag in ('existing-manifest', 'arithmetic-input', 'quote', 'event', 'research-reviews',
                 'pending-review-candidate', 'signed-review-response', 'review-trust-root', 'previous-review-response'):
        parser.add_argument('--' + flag + '-sha256')
    parser.add_argument(
        "--recommendation-schema-version",
        choices=(DECISION_RECOMMENDATION_SCHEMA, DECISION_RECOMMENDATION_V3_SCHEMA),
    )
    parser.add_argument("--schedule-request", type=Path, help="Hash-bound JSON scope request required to reopen an Evidence Stop.")
    parser.add_argument(
        "--resume-interrupted-after-consumption",
        action="store_true",
        help="Explicitly resume a previously admitted schedule after a recorded run failure.",
    )
    parser.add_argument("--interrupted-run-id")
    parser.add_argument('--prepare-review-response', action='store_true')
    parser.add_argument('--continuation-request', type=Path, help='Explicit unapproved ten-year research refresh request.')
    parser.add_argument('--continuation-request-sha256')
    args = parser.parse_args()
    resolve = lambda value: None if value is None else (value if value.is_absolute() else ROOT / value)
    package = resolve(args.package)
    output = resolve(args.output)
    if args.continuation_request is not None or args.continuation_request_sha256 is not None:
        incompatible = (args.package, args.schedule_request, args.existing_manifest, args.existing_manifest_sha256,
            args.arithmetic_input, args.arithmetic_input_sha256, args.quote, args.quote_sha256,
            args.event, args.event_sha256, args.research_reviews, args.research_reviews_sha256,
            args.pending_review_candidate, args.signed_review_response, args.review_trust_root,
            args.previous_review_response, args.pending_review_candidate_sha256,
            args.signed_review_response_sha256, args.review_trust_root_sha256,
            args.previous_review_response_sha256, args.recommendation_schema_version, args.interrupted_run_id)
        if (args.continuation_request is None or not args.continuation_request_sha256 or output is None
                or any(value is not None for value in incompatible) or args.prepare_review_response
                or args.resume_interrupted_after_consumption):
            parser.error('continuation refresh requires request/hash/output and excludes market/approval modes')
        from value_investment_agent.application.product.common import require_inside, load_json_object
        from value_investment_agent.application.research.product_continuation_candidate import refresh_product_continuation_candidate
        request_path = require_inside(ROOT, resolve(args.continuation_request), 'continuation request')
        if load_json_object(request_path, 'continuation request')['symbol'] != args.symbol:
            parser.error('continuation request differs from selected symbol')
        result = refresh_product_continuation_candidate(root=ROOT,
            request_binding=dict(path=request_path.relative_to(ROOT).as_posix(), sha256=args.continuation_request_sha256),
            output_dir=output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    from value_investment_agent.application.product.research_reviews import run_pending_review_command
    review_result = run_pending_review_command(root=ROOT, args=args)
    if review_result is not None:
        print(json.dumps(review_result, ensure_ascii=False, indent=2))
        return 0
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
    schedule_request, schedule_request_sha256 = load_schedule_request(
        ROOT, args.schedule_request
    )
    result = run_company_research_for_symbol(
        root=ROOT, symbol=args.symbol, package_path=package, output_path=output,
        schedule_request=schedule_request, schedule_request_sha256=schedule_request_sha256,
        quote_path=resolve(args.quote), quote_sha256=args.quote_sha256,
        event_path=resolve(args.event), event_sha256=args.event_sha256,
        reviews_path=resolve(args.research_reviews), reviews_sha256=args.research_reviews_sha256,
        recommendation_schema_version=args.recommendation_schema_version,
        resume_interrupted_after_consumption=args.resume_interrupted_after_consumption,
        interrupted_run_id=args.interrupted_run_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
