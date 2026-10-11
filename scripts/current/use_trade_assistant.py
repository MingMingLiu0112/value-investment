"""One local entry for viewing, updating and reviewing existing research."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'src')]

from value_investment_agent.application.product.user_research_workflow import read_published_research, selected_review_candidate, verify_user_update_registry
from value_investment_agent.presentation.user_research_workflow import render_published_research
from value_investment_agent.settings import get_settings
from value_investment_agent.application.product.common import sha256_file


def main() -> int:
    os.chdir(ROOT)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--mode', choices=('view', 'update', 'review'), default='view')
    parser.add_argument('--symbol')
    parser.add_argument('--details', action='store_true', help='Show all retained evidence and baseline gates.')
    parser.add_argument('--open', action='store_true', help='Open the verified canonical Excel.')
    parser.add_argument('advanced', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    advanced = args.advanced[1:] if args.advanced[:1] == ['--'] else args.advanced
    managed = {'--candidate', '--candidate-sha256', '--symbol', '--symbols', '--all-registered',
               '--case-registry', '--case-registry-sha256',
               '--pending-review-candidate', '--pending-review-candidate-sha256'}
    if any(value.split('=', 1)[0] in managed for value in advanced):
        parser.error('advanced options cannot replace the selected company or candidate')
    if args.open and args.mode != 'view':
        parser.error('--open is only available in view mode')
    if args.mode == 'update':
        workbook = get_settings().workbook_path.resolve()
        published = read_published_research(root=ROOT, workbook=workbook)
        symbols = [args.symbol] if args.symbol else list(published['pending_candidates'])
        if not symbols:
            parser.error('no published candidate registered for update')
        for symbol in symbols:
            selected_review_candidate(root=ROOT, published=published, symbol=symbol)
        registry_path = verify_user_update_registry(root=ROOT, published=published, symbols=symbols)
        command = [sys.executable, str(ROOT/'scripts/current/run_daily_trade_assistant.py')]
        command += ['--symbols', ','.join(symbols), '--case-registry', str(registry_path),
                    '--case-registry-sha256', sha256_file(registry_path)]
        return subprocess.call([*command, *advanced], cwd=ROOT)
    workbook = get_settings().workbook_path.resolve()
    published = read_published_research(root=ROOT, workbook=workbook)
    if args.mode == 'review':
        if not args.symbol:
            parser.error('review mode requires --symbol')
        binding = selected_review_candidate(root=ROOT, published=published, symbol=args.symbol)
        command = [sys.executable, str(ROOT/'scripts/current/review_research.py'),
                   '--symbol', args.symbol,
                   '--candidate', binding['path'], '--candidate-sha256', binding['sha256']]
        return subprocess.call([*command, *advanced], cwd=ROOT)
    if advanced:
        parser.error('view mode has no advanced mutation options')
    print(render_published_research(published, [args.symbol] if args.symbol else None, details=args.details))
    if args.open:
        if os.name != 'nt':
            parser.error('--open is supported on Windows')
        os.startfile(workbook)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
