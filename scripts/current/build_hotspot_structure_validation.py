"""Build the immutable W7 hotspot structure-validation evidence package."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.hotspot.validation_evidence import (  # noqa: E402
    build_hotspot_structure_validation,
    write_hotspot_structure_validation,
)


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timestamp must be ISO-8601") from error
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed


def _sha256(value: str) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise argparse.ArgumentTypeError("SHA-256 must be 64 lowercase hexadecimal characters")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-report", type=Path, required=True)
    parser.add_argument("--selection-report-sha256", type=_sha256, required=True)
    parser.add_argument(
        "--current-price-conditions",
        type=Path,
        default=Path("config/current-price-conditions.json"),
    )
    parser.add_argument("--historical-case", type=Path, action="append", default=[])
    parser.add_argument("--incomplete-live-directory", type=Path)
    parser.add_argument("--incomplete-live-reason")
    parser.add_argument("--evaluated-at", type=_timestamp)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    report = build_hotspot_structure_validation(
        root=ROOT,
        selection_report_path=args.selection_report,
        selection_report_sha256=args.selection_report_sha256,
        current_price_conditions_path=args.current_price_conditions,
        historical_case_paths=args.historical_case,
        incomplete_live_directory=args.incomplete_live_directory,
        incomplete_live_reason=args.incomplete_live_reason,
        evaluated_at=args.evaluated_at,
    )
    manifest = write_hotspot_structure_validation(
        report,
        root=ROOT,
        output_dir=args.output_dir,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
