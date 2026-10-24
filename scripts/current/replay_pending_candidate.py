"""Prepare an immutable exact-input successor and a Web supplement manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from value_investment_agent.application.product.pending_candidate_replay import prepare_pending_candidate_replay
from value_investment_agent.application.product.pending_replay_publication import prepare_pending_replay_publication


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--predecessor', type=Path, required=True)
    parser.add_argument('--predecessor-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare_pending_candidate_replay(root=ROOT,
        predecessor_path=ROOT / args.predecessor, predecessor_sha256=args.predecessor_sha256,
        output_dir=ROOT / args.output)
    result['publication'] = prepare_pending_replay_publication(root=ROOT,
        candidate_binding=result['candidate_binding'], output_path=ROOT / args.output / 'publication.json')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
