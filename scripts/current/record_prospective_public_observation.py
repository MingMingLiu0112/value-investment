"""Append one verified public CNINFO observation; never decide materiality."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product.prospective_observation import (  # noqa: E402
    append_cninfo_observation,
    append_reviewed_cninfo_notice_observation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration", required=True)
    parser.add_argument("--registration-sha256", required=True)
    parser.add_argument("--scan-receipt", required=True)
    parser.add_argument("--scan-receipt-sha256", required=True)
    parser.add_argument("--interpretation")
    parser.add_argument("--interpretation-sha256")
    parser.add_argument("--document-review")
    parser.add_argument("--document-review-sha256")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--supersedes-observation-id")
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    if args.document_review or args.document_review_sha256:
        if (
            not args.document_review or not args.document_review_sha256
            or args.interpretation or args.interpretation_sha256
        ):
            parser.error("review mode requires both --document-review options and excludes legacy interpretation options")
        result = append_reviewed_cninfo_notice_observation(
            root=ROOT, registration_path=args.registration,
            registration_sha256=args.registration_sha256,
            scan_receipt_path=args.scan_receipt,
            scan_receipt_sha256=args.scan_receipt_sha256,
            document_review_path=args.document_review,
            document_review_sha256=args.document_review_sha256,
            symbol=args.symbol, document_id=args.document_id, output_dir=output_dir,
            supersedes_observation_id=args.supersedes_observation_id,
        )
    else:
        if not args.interpretation or not args.interpretation_sha256:
            parser.error("legacy scan mode requires both --interpretation options")
        result = append_cninfo_observation(
            root=ROOT, registration_path=args.registration,
            registration_sha256=args.registration_sha256,
            scan_receipt_path=args.scan_receipt,
            scan_receipt_sha256=args.scan_receipt_sha256,
            interpretation_path=args.interpretation,
            interpretation_sha256=args.interpretation_sha256,
            symbol=args.symbol, document_id=args.document_id,
            output_dir=output_dir,
            supersedes_observation_id=args.supersedes_observation_id,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
