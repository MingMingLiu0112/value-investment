"""Run the maintained institution collector for one explicit issuer."""
import argparse
import json
from value_investment_agent.institution_metrics import collect_institution_metrics


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('symbol', nargs='+')
    args = parser.parse_args()
    if len(args.symbol) > 10 or len(set(args.symbol)) != len(args.symbol) or any(
            len(s) != 6 or not s.isascii() or not s.isdigit() for s in args.symbol):
        parser.error('Expected one to ten unique six-digit symbols')
    result = collect_institution_metrics(limit=len(args.symbol), symbols=args.symbol)
    print(json.dumps(result, ensure_ascii=False))
    if result.get('failures'):
        raise SystemExit(1)
