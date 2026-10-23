"""Draft local group responses or consume a reviewer-provided signed response."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from value_investment_agent.application.product.research_review_wizard import (
    draft_pending_review_response, preview_pending_review_response, render_review_preview,
)
from value_investment_agent.application.product.research_reviews import run_pending_review_command
from value_investment_agent.application.product.common import require_inside, sha256_file


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--verify-economics', action='store_true',
        help='Build a source-bound economic review bundle; never approve G3. Exit 2 means not admitted.')
    parser.add_argument('--candidate', '--pending-review-candidate',
        dest='pending_review_candidate', type=Path)
    parser.add_argument('--candidate-sha256', '--pending-review-candidate-sha256',
        dest='pending_review_candidate_sha256')
    parser.add_argument('--prepare-bound-draft', action='store_true',
        help='Prepare exact source-bound inputs for review without changing economic assumptions or approving them.')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--preview', action='store_true', help='Read-only noninteractive review preview.')
    parser.add_argument('--advanced-preview', action='store_true', help='Include exact hashes in read-only preview.')
    parser.add_argument('--resume-incomplete', action='store_true')
    parser.add_argument('--incomplete-consumption-sha256')
    for role in ('signed-review-response', 'review-trust-root', 'previous-review-response'):
        parser.add_argument('--' + role, type=Path)
        parser.add_argument('--' + role + '-sha256')
    parser.set_defaults(prepare_review_response=False, **{name: None for name in (
        'package', 'existing_manifest', 'existing_manifest_sha256', 'arithmetic_input',
        'arithmetic_input_sha256', 'quote', 'quote_sha256', 'event', 'event_sha256',
        'research_reviews', 'research_reviews_sha256', 'schedule_request',
        'recommendation_schema_version')})
    args = parser.parse_args()
    if args.verify_economics:
        if (args.output is None or args.prepare_bound_draft or args.preview or args.advanced_preview
                or args.pending_review_candidate or args.pending_review_candidate_sha256
                or args.resume_incomplete or args.incomplete_consumption_sha256
                or any(getattr(args, name) is not None for name in (
                    'signed_review_response', 'signed_review_response_sha256',
                    'review_trust_root', 'review_trust_root_sha256',
                    'previous_review_response', 'previous_review_response_sha256'))):
            parser.error('economic verification requires --output and excludes approval/draft inputs')
        from value_investment_agent.application.research.economic_review_bundle import build_current_economic_review_bundle
        from value_investment_agent.application.product.common import write_new_json
        output = require_inside(ROOT / 'runtime', ROOT / args.output, 'economic verification output')
        result = build_current_economic_review_bundle(root=ROOT, symbol=args.symbol,
            now=datetime.now(timezone.utc))
        write_new_json(output, result)
        print(json.dumps(dict(symbol=args.symbol, report=str(output.relative_to(ROOT)),
            sha256=sha256_file(output), primary_valuation_usable=result['primary_valuation_usable'],
            action='no_order'), ensure_ascii=False, indent=2))
        return 0 if result['primary_valuation_usable'] is True else 2
    if args.prepare_bound_draft:
        if (args.output is None or args.pending_review_candidate is not None
                or args.pending_review_candidate_sha256 is not None
                or args.preview or args.advanced_preview or args.resume_incomplete
                or args.incomplete_consumption_sha256 is not None
                or any(getattr(args, role) is not None for role in (
                    'signed_review_response', 'signed_review_response_sha256',
                    'review_trust_root', 'review_trust_root_sha256',
                    'previous_review_response', 'previous_review_response_sha256'))):
            parser.error('bound-draft preparation requires --output and excludes candidate/signature/preview inputs')
        from value_investment_agent.application.product.bound_draft_review import prepare_bound_draft_review_candidate
        result = prepare_bound_draft_review_candidate(root=ROOT, symbol=args.symbol,
            output_dir=ROOT / args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.pending_review_candidate is None or args.pending_review_candidate_sha256 is None:
        parser.error('review requires --candidate and --candidate-sha256')
    args.preview = args.preview or args.advanced_preview
    if args.resume_incomplete and args.output is None:
        parser.error('resume requires --output pointing to the original incomplete directory')
    if args.preview and args.signed_review_response is not None:
        parser.error('preview excludes signed consumption')
    if not args.preview and args.output is None:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        directory = 'research-review-consumptions' if args.signed_review_response else 'research-review-drafts'
        name = stamp + '-' + args.symbol + ('' if args.signed_review_response else '.json')
        args.output = Path('runtime') / directory / name
    if args.signed_review_response is not None:
        for role in ('signed_review_response', 'review_trust_root', 'previous_review_response'):
            value = getattr(args, role)
            if value is not None and getattr(args, role + '_sha256') is None:
                source = require_inside(ROOT, ROOT / value, role)
                setattr(args, role + '_sha256', sha256_file(source))
        result = run_pending_review_command(root=ROOT, args=args)
    else:
        if any(getattr(args, name) is not None for name in ('signed_review_response_sha256',
                'review_trust_root', 'review_trust_root_sha256', 'previous_review_response',
                'previous_review_response_sha256', 'incomplete_consumption_sha256')) or args.resume_incomplete:
            parser.error('draft mode excludes signature, trust and previous-response inputs')
        from value_investment_agent.application.product.research_reviews import prepare_pending_review_response
        candidate = ROOT / args.pending_review_candidate
        template = prepare_pending_review_response(root=ROOT, candidate_path=candidate,
            candidate_sha256=args.pending_review_candidate_sha256)
        if template['symbol'] != args.symbol:
            parser.error('review candidate issuer mismatch')
        if args.preview:
            if args.output is not None:
                parser.error('preview writes nothing and excludes --output')
            result = preview_pending_review_response(root=ROOT, candidate_path=candidate,
                candidate_sha256=args.pending_review_candidate_sha256)
            print(render_review_preview(result, advanced=args.advanced_preview))
            return 0
        else:
            result = draft_pending_review_response(root=ROOT, candidate_path=candidate,
                candidate_sha256=args.pending_review_candidate_sha256, output_path=ROOT / args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
