"""Refresh the scoped public A+B screen; no accounts, approvals, or orders."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-public-network',action='store_true')
    args=parser.parse_args()
    from value_investment_agent.application.discovery.sse_main_screening import refresh
    result=refresh(root=ROOT,allow_network=args.allow_public_network)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
