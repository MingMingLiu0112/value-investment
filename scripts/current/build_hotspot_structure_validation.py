"""Build the immutable W7 hotspot structure-validation evidence package."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
    parser.add_argument('--independent-audit', action='store_true',
        help='Audit current independent strategy evidence without creating a release; exit 2 if not admitted.')
    parser.add_argument('--selection-history-spec', type=Path,
        help='Replay bound daily snapshots; exit 0 means complete replay, never strategy admission.')
    parser.add_argument('--selection-history-sha256', type=_sha256)
    parser.add_argument("--selection-report", type=Path)
    parser.add_argument("--selection-report-sha256", type=_sha256)
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
    if args.selection_history_spec is not None:
        if (args.independent_audit or not args.selection_history_sha256 or args.selection_report
                or args.selection_report_sha256 or args.historical_case or args.incomplete_live_directory
                or args.incomplete_live_reason
                or args.current_price_conditions != Path('config/current-price-conditions.json')):
            parser.error('history replay requires an exact specification hash and excludes other modes')
        from value_investment_agent.application.hotspot.selection_history import replay_selection_history
        from value_investment_agent.application.hotspot.event_replay import _bound_bytes
        from value_investment_agent.application.product.common import require_inside, write_new_json, sha256_file
        source = dict(path=args.selection_history_spec.as_posix(), sha256=args.selection_history_sha256)
        specification = json.loads(_bound_bytes(ROOT, source))
        output = require_inside(ROOT / 'runtime', ROOT / args.output_dir, 'history output') / 'selection-history.json'
        report = replay_selection_history(root=ROOT, specification=specification,
            now=args.evaluated_at or datetime.now(timezone.utc))
        write_new_json(output, report)
        print(json.dumps(dict(report=str(output.relative_to(ROOT)), sha256=sha256_file(output),
            status=report['status'], strategy_validation=report['strategy_validation'], action='no_order')))
        return 0 if report['status'] == 'REPLAYED' else 2
    if args.selection_history_sha256:
        parser.error('--selection-history-sha256 requires --selection-history-spec')
    if args.independent_audit:
        if (args.selection_report or args.selection_report_sha256 or args.historical_case
                or args.incomplete_live_directory or args.incomplete_live_reason
                or args.current_price_conditions != Path('config/current-price-conditions.json')):
            parser.error('independent audit reads registered current sources, not injected alternatives')
        from value_investment_agent.application.hotspot.independent_validation import validate_current_hotspot_strategy
        from value_investment_agent.application.product.common import require_inside, write_new_json, sha256_file
        output = require_inside(ROOT / 'runtime', ROOT / args.output_dir, 'independent audit output') / 'independent-validation.json'
        report = validate_current_hotspot_strategy(root=ROOT, now=args.evaluated_at or datetime.now(timezone.utc))
        write_new_json(output, report)
        print(json.dumps(dict(report=str(output.relative_to(ROOT)), sha256=sha256_file(output),
            strategy_validation=report['strategy_validation'], action='no_order'), indent=2))
        return 0 if report['strategy_validation'] == 'PASSED' else 2
    if args.selection_report is None or args.selection_report_sha256 is None:
        parser.error('structure validation requires --selection-report and --selection-report-sha256')

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
