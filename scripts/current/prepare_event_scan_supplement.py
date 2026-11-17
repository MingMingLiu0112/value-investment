"""Prepare an independent unsigned event-review version; never publish or approve."""
import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from value_investment_agent.application.product.event_scan_supplement import prepare_event_scan_supplement


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--package', required=True)
    parser.add_argument('--package-sha256', required=True)
    parser.add_argument('--observation', nargs=2, action='append', required=True,
                        metavar=('PATH', 'SHA256'))
    parser.add_argument('--coverage-from', type=date.fromisoformat, required=True)
    parser.add_argument('--review-cutoff', type=date.fromisoformat, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare_event_scan_supplement(root=ROOT,
        package_binding=dict(path=args.package, sha256=args.package_sha256),
        observation_bindings=[dict(path=path, sha256=digest) for path, digest in args.observation],
        coverage_from=args.coverage_from, review_cutoff=args.review_cutoff,
        output_dir=ROOT / args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
