"""Run one hash-bound research validity review for a registered symbol."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from value_investment_agent.application.product.common import sha256_file  # noqa: E402
from value_investment_agent.application.product.research_validity_review import (  # noqa: E402
    render_research_validity_review_markdown, review_research_validity)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--package-sha256", required=True)
    parser.add_argument("--review-cutoff", required=True,
                        help="ISO date the review must cover, e.g. the verified close date.")
    parser.add_argument("--event-scan", type=Path, required=True)
    parser.add_argument("--event-scan-sha256", required=True)
    parser.add_argument("--quote-bundle", type=Path,
                        help="Optional registered close bundle for the price ladder.")
    parser.add_argument("--quote-bundle-sha256")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path)
    args = parser.parse_args()
    if (args.quote_bundle is None) != (args.quote_bundle_sha256 is None):
        parser.error("quote bundle requires both path and SHA-256")
    review = review_research_validity(
        root=ROOT, symbol=args.symbol, package_path=args.package,
        package_sha256=args.package_sha256,
        review_cutoff=date.fromisoformat(args.review_cutoff),
        event_scan_path=args.event_scan, event_scan_sha256=args.event_scan_sha256,
        quote_bundle=args.quote_bundle, quote_bundle_sha256=args.quote_bundle_sha256,
        output_path=args.output, today=datetime.now(timezone.utc))
    result = {"symbol": review["symbol"], "status": review["status"],
              "artifact": args.output.as_posix(),
              "artifact_sha256": sha256_file(ROOT / args.output),
              "action": "no_order"}
    if args.output_markdown is not None:
        markdown_path = ROOT / args.output_markdown
        if markdown_path.exists():
            raise FileExistsError(f"refusing to overwrite: {markdown_path}")
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_research_validity_review_markdown(review),
                                 encoding="utf-8")
        result["markdown"] = args.output_markdown.as_posix()
        result["markdown_sha256"] = sha256_file(markdown_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
