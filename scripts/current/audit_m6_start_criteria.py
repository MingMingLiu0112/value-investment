"""Print the read-only M6 start-criteria matrix; never request authorization."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.operations.start_criteria import (  # noqa: E402
    load_m6_start_criteria_matrix,
)
from value_investment_agent.operations.shadow_daily_input import audit_shadow_daily_input
from value_investment_agent.operations.shadow_daily_run import run_isolated_daily_attempt
from value_investment_agent.application.product.common import write_new_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix",
        type=Path,
        default=ROOT / "config" / "m6-start-criteria-matrix-v1.json",
    )
    parser.add_argument('--daily-input', type=Path)
    parser.add_argument('--daily-input-sha256')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--isolated-run', type=Path)
    parser.add_argument('--symbol')
    parser.add_argument('--event-input', type=Path)
    parser.add_argument('--event-input-sha256')
    parser.add_argument('--quote-input', type=Path)
    parser.add_argument('--quote-input-sha256')
    parser.add_argument('--research-package', type=Path)
    parser.add_argument('--research-package-sha256')
    parser.add_argument('--schedule-request', type=Path)
    parser.add_argument('--schedule-request-sha256')
    parser.add_argument('--event-followup', type=Path)
    parser.add_argument('--event-followup-sha256')
    args = parser.parse_args()
    if args.isolated_run:
        if not all((args.symbol, args.event_input, args.event_input_sha256)) or args.daily_input or args.output:
            parser.error('isolated run requires symbol/event path/hash and excludes daily-input/output')
        print(json.dumps(run_isolated_daily_attempt(root=ROOT, output=ROOT / args.isolated_run,
            symbol=args.symbol, event_path=ROOT / args.event_input,
            event_sha256=args.event_input_sha256,
            quote_path=None if args.quote_input is None else ROOT / args.quote_input,
            quote_sha256=args.quote_input_sha256,
            package_path=None if args.research_package is None else ROOT / args.research_package,
            package_sha256=args.research_package_sha256,
            schedule_request_path=None if args.schedule_request is None else ROOT / args.schedule_request,
            schedule_request_sha256=args.schedule_request_sha256,
            followup_path=None if args.event_followup is None else ROOT / args.event_followup,
            followup_sha256=args.event_followup_sha256), ensure_ascii=False, indent=2))
        return 0
    if any((args.research_package, args.research_package_sha256,
            args.schedule_request, args.schedule_request_sha256,
            args.event_followup, args.event_followup_sha256)):
        parser.error('research package/schedule request require isolated-run')
    if bool(args.daily_input) != bool(args.daily_input_sha256):
        raise ValueError('daily input requires paired path/hash')
    matrix_path = args.matrix if args.matrix.is_absolute() else ROOT / args.matrix
    matrix = load_m6_start_criteria_matrix(matrix_path, root=ROOT)
    payload = matrix.as_policy()
    payload["state_semantics"] = "STATIC_BASELINE_NOT_CURRENT_READINESS"
    payload["current_status_source"] = "latest verified m6 operational preflight receipt"
    if args.daily_input:
        payload['daily_input_audit'] = audit_shadow_daily_input(root=ROOT,
            path=ROOT / args.daily_input, expected_sha256=args.daily_input_sha256,
            now=datetime.now(timezone.utc))
    if args.output:
        target = (ROOT / args.output).resolve()
        if not target.is_relative_to(ROOT / 'runtime'):
            raise ValueError('audit output must stay under runtime')
        write_new_json(target, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
