"""Build a symbol-neutral current-workbench request from shared research output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product import build_current_workbench_for_symbol  # noqa: E402
from value_investment_agent.domain.decision.decision_recommendation import (  # noqa: E402
    DECISION_RECOMMENDATION_SCHEMA, DECISION_RECOMMENDATION_V3_SCHEMA,
)
from value_investment_agent.presentation.read_models.existing_research_report import render_existing_research_report, render_current_research_readiness  # noqa: E402
from value_investment_agent.application.product.common import load_json_object, sha256_file, require_inside  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--existing-manifest", type=Path)
    parser.add_argument("--existing-manifest-sha256")
    parser.add_argument("--arithmetic-input", type=Path)
    parser.add_argument("--arithmetic-input-sha256")
    parser.add_argument("--quote", type=Path)
    parser.add_argument("--quote-sha256")
    parser.add_argument("--event", type=Path)
    parser.add_argument("--event-sha256")
    parser.add_argument("--research-reviews", type=Path)
    parser.add_argument("--research-reviews-sha256")
    parser.add_argument("--schedule-request", type=Path)
    parser.add_argument(
        "--recommendation-schema-version",
        choices=(DECISION_RECOMMENDATION_SCHEMA, DECISION_RECOMMENDATION_V3_SCHEMA),
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    package = None if args.package is None else (
        args.package if args.package.is_absolute() else ROOT / args.package
    )
    output = args.output if args.output.is_absolute() else ROOT / args.output
    resolve = lambda path: None if path is None else (path if path.is_absolute() else ROOT / path)
    request = None
    request_sha256 = None
    if args.schedule_request is not None:
        request_path = require_inside(ROOT, resolve(args.schedule_request), "schedule request")
        request_sha256 = sha256_file(request_path)
        request = load_json_object(request_path, "schedule request")
        if sha256_file(request_path) != request_sha256:
            raise ValueError("schedule request changed during loading")
    report = None if args.report is None else (ROOT / args.report).resolve()
    if report is not None:
        if not report.is_relative_to((ROOT / "runtime").resolve()) or report.exists():
            parser.error("report requires a new runtime path")
    result = build_current_workbench_for_symbol(
        root=ROOT,
        symbol=args.symbol,
        package_path=package,
        output_path=output,
        existing_manifest_path=None if args.existing_manifest is None else ROOT / args.existing_manifest,
        existing_manifest_sha256=args.existing_manifest_sha256,
        arithmetic_input_path=None if args.arithmetic_input is None else ROOT / args.arithmetic_input,
        arithmetic_input_sha256=args.arithmetic_input_sha256,
        schedule_request=request,
        schedule_request_sha256=request_sha256,
        quote_path=resolve(args.quote), quote_sha256=args.quote_sha256,
        event_path=resolve(args.event), event_sha256=args.event_sha256,
        reviews_path=resolve(args.research_reviews),
        reviews_sha256=args.research_reviews_sha256,
        recommendation_schema_version=args.recommendation_schema_version,
    )
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8", newline="\n") as stream:
            renderer = render_existing_research_report if args.existing_manifest is not None else render_current_research_readiness
            stream.write(renderer(result["result"]))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
