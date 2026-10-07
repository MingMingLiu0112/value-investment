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
from value_investment_agent.operations.shadow_daily_input import audit_shadow_daily_input, consume_shadow_daily_input
from value_investment_agent.operations.shadow_daily_run import run_isolated_daily_attempt
from value_investment_agent.application.product.common import sha256_file, write_new_json
from value_investment_agent.operations.personal_shadow_governance import assess_personal_observation_dependencies
from value_investment_agent.operations.personal_shadow_observation import append_offline_observation
from value_investment_agent.operations.shadow_daily_review_publication import render_bound_daily_review


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
    parser.add_argument('--simulated-portfolio', type=Path)
    parser.add_argument('--simulated-portfolio-sha256')
    parser.add_argument('--operational-inputs', type=Path)
    parser.add_argument('--operational-inputs-sha256')
    parser.add_argument('--research-reviews', type=Path)
    parser.add_argument('--research-reviews-sha256')
    parser.add_argument('--governance-profile', choices=('legacy-v1', 'personal-observation-v1'), default='legacy-v1')
    parser.add_argument('--offline-observation-ledger', type=Path,
                        help='Append an offline-only audit attempt under runtime; never count a real session.')
    parser.add_argument('--expected-ledger-head-sha256')
    parser.add_argument('--daily-review-output', type=Path,
                        help='Re-render a hash-bound no_order company card under runtime.')
    args = parser.parse_args()
    if bool(args.offline_observation_ledger) != bool(args.expected_ledger_head_sha256):
        parser.error('offline observation ledger requires its externally retained head hash')
    if args.daily_review_output:
        if (not args.daily_input or not args.daily_input_sha256 or args.isolated_run
                or args.offline_observation_ledger or args.operational_inputs
                or args.operational_inputs_sha256 or args.output or any((
                    args.symbol, args.event_input, args.event_input_sha256,
                    args.quote_input, args.quote_input_sha256,
                    args.research_package, args.research_package_sha256,
                    args.schedule_request, args.schedule_request_sha256,
                    args.event_followup, args.event_followup_sha256,
                    args.simulated_portfolio, args.simulated_portfolio_sha256,
                    args.research_reviews, args.research_reviews_sha256,
                ))):
            parser.error('daily review requires daily-input path/hash and no execution inputs')
        target = (ROOT / args.daily_review_output).resolve()
        if not target.is_relative_to((ROOT / 'runtime').resolve()):
            parser.error('daily review output must stay under runtime')
        card = render_bound_daily_review(root=ROOT, manifest_path=ROOT / args.daily_input,
            manifest_sha256=args.daily_input_sha256, now=datetime.now(timezone.utc))
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf-8') as handle:
            handle.write(card)
        print(json.dumps(dict(output=str(target), output_sha256=sha256_file(target),
            action='no_order', verified_real_session_count=0), ensure_ascii=False, indent=2))
        return 0
    if args.offline_observation_ledger:
        if (args.governance_profile != 'personal-observation-v1' or not args.daily_input
                or not args.daily_input_sha256 or args.isolated_run or args.operational_inputs
                or args.operational_inputs_sha256 or args.output or any((
                    args.symbol, args.event_input, args.event_input_sha256,
                    args.quote_input, args.quote_input_sha256,
                    args.research_package, args.research_package_sha256,
                    args.schedule_request, args.schedule_request_sha256,
                    args.event_followup, args.event_followup_sha256,
                    args.simulated_portfolio, args.simulated_portfolio_sha256,
                    args.research_reviews, args.research_reviews_sha256,
                ))):
            parser.error('offline observation requires personal profile and daily-input path/hash only')
        ledger = (ROOT / args.offline_observation_ledger).resolve()
        if not ledger.is_relative_to((ROOT / 'runtime').resolve()):
            parser.error('offline observation ledger must stay under runtime')
        result = append_offline_observation(root=ROOT, ledger=ledger,
            manifest=ROOT / args.daily_input,
            expected_manifest_sha256=args.daily_input_sha256,
            expected_head_sha256=args.expected_ledger_head_sha256,
            now=datetime.now(timezone.utc))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.isolated_run:
        if args.governance_profile != 'legacy-v1':
            parser.error('governance assessment is separate from isolated execution')
        if args.operational_inputs or args.operational_inputs_sha256:
            parser.error('operational consumption requires daily-input, not isolated-run')
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
            followup_sha256=args.event_followup_sha256,
            simulated_portfolio_path=None if args.simulated_portfolio is None else ROOT / args.simulated_portfolio,
            simulated_portfolio_sha256=args.simulated_portfolio_sha256,
            reviews_path=None if args.research_reviews is None else ROOT / args.research_reviews,
            reviews_sha256=args.research_reviews_sha256), ensure_ascii=False, indent=2))
        return 0
    if any((args.research_package, args.research_package_sha256,
            args.schedule_request, args.schedule_request_sha256,
            args.event_followup, args.event_followup_sha256,
            args.simulated_portfolio, args.simulated_portfolio_sha256,
            args.research_reviews, args.research_reviews_sha256)):
        parser.error('research package/schedule request require isolated-run')
    if bool(args.daily_input) != bool(args.daily_input_sha256):
        raise ValueError('daily input requires paired path/hash')
    if (args.operational_inputs or args.operational_inputs_sha256) and not args.daily_input:
        parser.error('operational inputs require daily-input')
    matrix_path = args.matrix if args.matrix.is_absolute() else ROOT / args.matrix
    matrix = load_m6_start_criteria_matrix(matrix_path, root=ROOT)
    payload = matrix.as_policy()
    payload["state_semantics"] = "STATIC_BASELINE_NOT_CURRENT_READINESS"
    payload["current_status_source"] = "latest verified m6 operational preflight receipt"
    if args.governance_profile == 'personal-observation-v1':
        payload['personal_observation_assessment'] = assess_personal_observation_dependencies(payload)
    if args.daily_input:
        payload['daily_consumer'] = consume_shadow_daily_input(root=ROOT,
            path=ROOT / args.daily_input, expected_sha256=args.daily_input_sha256,
            now=datetime.now(timezone.utc),
            operational_inputs=None if args.operational_inputs is None else ROOT / args.operational_inputs,
            operational_inputs_sha256=args.operational_inputs_sha256)
        payload['daily_input_audit'] = payload['daily_consumer']['audit']
    if args.output:
        target = (ROOT / args.output).resolve()
        if not target.is_relative_to(ROOT / 'runtime'):
            raise ValueError('audit output must stay under runtime')
        write_new_json(target, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
