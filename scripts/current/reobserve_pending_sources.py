"""Reobserve retained source bytes and optionally run the existing pending candidate use case."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.source_reobservation import (
    prepare_source_reobservation, run_reobserved_candidate,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--symbol', required=True)
    for role in ('case-registry', 'policy', 'reference-manifest', 'reference-script'):
        parser.add_argument('--' + role, type=Path, required=True)
        parser.add_argument('--' + role + '-sha256', required=True)
    parser.add_argument('--source-id', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate-choice', help='Run one existing finite choice, without signing or registration.')
    args = parser.parse_args()
    binding = lambda role: dict(path=getattr(args, role).as_posix(), sha256=getattr(args, role + '_sha256'))
    output = ROOT / args.output
    result = prepare_source_reobservation(root=ROOT, case_registry_binding=binding('case_registry'),
        symbol=args.symbol, policy_binding=binding('policy'), source_ids=args.source_id,
        reference_manifest_binding=binding('reference_manifest'),
        reference_script_binding=binding('reference_script'), output_dir=output)
    if args.candidate_choice:
        manifest = output / 'manifest.json'
        result = run_reobserved_candidate(root=ROOT,
            binding=dict(path=manifest.relative_to(ROOT).as_posix(), sha256=sha256_file(manifest)),
            choice_id=args.candidate_choice)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
