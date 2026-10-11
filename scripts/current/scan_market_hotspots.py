"""Manual retained-data hotspot observation; permanently no_order."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from value_investment_agent.application.hotspot.manual import run_manual_scan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir','--output',dest='output',type=Path,required=True)
    parser.add_argument('--offline-bundle',type=Path)
    parser.add_argument('--offline-bundle-sha256')
    parser.add_argument('--cutoff',default=None,help='Timezone-aware observation cutoff, not a historical PIT claim')
    args=parser.parse_args()
    result=run_manual_scan(root=ROOT,output=args.output.resolve(),offline_bundle=args.offline_bundle.resolve() if args.offline_bundle else None,
        offline_sha256=args.offline_bundle_sha256,cutoff=datetime.fromisoformat(args.cutoff) if args.cutoff else None)
    print(json.dumps(result))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
