"""Prepare external materiality handoff or import a scoped signed response (no_order)."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from value_investment_agent.application.product.common import require_inside, write_new_json, sha256_file
from value_investment_agent.application.product.research_materiality_reviews import (
    prepare_materiality_review_handoff, consume_materiality_review_response,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest='mode', required=True)
    prepare = commands.add_parser('prepare', allow_abbrev=False)
    consume = commands.add_parser('consume', allow_abbrev=False)
    recheck = commands.add_parser('recheck', allow_abbrev=False)
    recheck.add_argument('--symbol', required=True)
    recheck.add_argument('--output', type=Path, required=True)
    consume.add_argument('--resume-incomplete', action='store_true')
    consume.add_argument('--incomplete-consumption-sha256')
    for command, roles in ((prepare, ('package', 'scan')),
                           (consume, ('handoff', 'response', 'trust-root'))):
        for role in roles:
            command.add_argument('--' + role, type=Path, required=True)
            command.add_argument('--' + role + '-sha256', required=True)
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        result = prepare_materiality_review_handoff(root=ROOT,
            package_path=ROOT / args.package, package_sha256=args.package_sha256,
            scan_path=ROOT / args.scan, scan_sha256=args.scan_sha256)
        output = require_inside(ROOT / 'runtime', ROOT / args.output, 'materiality handoff')
        write_new_json(output, result)
        result = dict(status='EXTERNAL_SIGNATURE_REQUIRED', action='no_order',
            handoff_binding=dict(path=output.relative_to(ROOT).as_posix(), sha256=sha256_file(output)))
    elif args.mode == 'consume':
        result = consume_materiality_review_response(root=ROOT,
            handoff_path=ROOT / args.handoff, handoff_sha256=args.handoff_sha256,
            response_path=ROOT / args.response, response_sha256=args.response_sha256,
            trust_root_path=ROOT / args.trust_root, trust_root_sha256=args.trust_root_sha256,
            output_dir=ROOT / args.output, resume_incomplete=args.resume_incomplete,
            incomplete_consumption_sha256=args.incomplete_consumption_sha256)
    else:
        from datetime import datetime, timezone
        from value_investment_agent.application.product.quote_bridge import execute_quote_bridge_for_symbol
        result = execute_quote_bridge_for_symbol(root=ROOT, symbol=args.symbol,
            today=datetime.now(timezone.utc))
        output = require_inside(ROOT / 'runtime', ROOT / args.output, 'materiality recheck')
        write_new_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
