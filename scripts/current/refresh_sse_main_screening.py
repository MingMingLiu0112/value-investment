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
    parser.add_argument('--financial-only',action='store_true',help='Supplement same-period financial originals without restamping retained quotes')
    parser.add_argument('--comparison-batches',type=int,default=1,help='Finite Sina batches of up to six issuers, maximum ten')
    parser.add_argument('--research-cycle', action='store_true', help='Run existing screening, bounded enrichment and final consumption as one public cycle')
    parser.add_argument('--reuse-public-snapshot', action='store_true', help='Explicit retained-source mode; does not refresh or restamp quotes')
    parser.add_argument('--research-batches', type=int, default=1)
    parser.add_argument('--tracking-budget', type=int, default=30)
    parser.add_argument('--operating-research-budget', type=int, default=0, help='Explicit model tasks, maximum three; existing provider authorization and CNY daily cap still apply')
    args=parser.parse_args()
    if not args.research_cycle and args.operating_research_budget:
        parser.error('operating research budget requires explicit research cycle')
    if args.reuse_public_snapshot and (not args.research_cycle or args.financial_only):
        parser.error('retained snapshot requires research cycle and cannot mix with financial-only refresh')
    if args.research_cycle:
        from datetime import datetime, timezone
        from uuid import uuid4
        from value_investment_agent.application.research.sse_value_refresh_v1 import run_value_research_refresh
        output=ROOT/'runtime/sse-value-auto-refresh'/('cycle-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8])
        result=run_value_research_refresh(root=ROOT, output_dir=output,
            source_mode='RETAINED' if args.reuse_public_snapshot else 'FINANCIAL' if args.financial_only else 'FRESH',
            allow_network=args.allow_public_network, tracking_budget=args.tracking_budget,
            enrichment_batches=args.research_batches, comparison_batches=args.comparison_batches,
            operating_budget=args.operating_research_budget,
            on_stage=lambda event: print(json.dumps(event,ensure_ascii=False),flush=True))
        print(json.dumps(dict(status=result['status'],receipt=str(output/'cycle.json'),action='no_order'),ensure_ascii=False))
        return 2 if result['status'] == 'FAILED' else 130 if result['status'] == 'CANCELLED' else 0
    from value_investment_agent.application.discovery.sse_main_screening import refresh,enrich_current
    result=(enrich_current if args.financial_only else refresh)(root=ROOT,allow_network=args.allow_public_network,comparison_batches=args.comparison_batches)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    raise SystemExit(main())
