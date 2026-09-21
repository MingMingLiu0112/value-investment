"""Rank evidence work, not stocks to buy, from the actual exported decision gates."""
import argparse
import json
from collections import Counter
from pathlib import Path

from value_investment_agent.financial_quality import GENERAL_FIELDS, _accepted
from value_investment_agent.financial_institutions import provisional_financial_type
from value_investment_agent.reminders import build_reminders


def audit(payload, period):
    points = {}
    for point in payload.get('points', []) + payload.get('annual_points', []):
        if str(point.get('period_label')) != period:
            continue
        key = (point['symbol'], point['field_name'])
        previous = points.get(key)
        rank = (str(point.get('created_at', '')), str(point.get('fetched_at', '')))
        if previous is None or rank > previous[0]:
            points[key] = (rank, point)
    companies = []
    totals = Counter()
    for company in payload['market_candidates']:
        if provisional_financial_type(company.get('name'), company.get('sector')):
            continue
        gaps = {}
        for field in GENERAL_FIELDS:
            point = points.get((company['symbol'], field), (None, None))[1]
            if not _accepted(point):
                gaps[field] = 'missing' if point is None else 'not_accepted'
                totals[field] += 1
        companies.append({'symbol': company['symbol'], 'name': company['name'],
                          'gap_count': len(gaps), 'gaps': gaps})
    reminders = build_reminders(payload)
    return {'export_generated_at': payload['generated_at'], 'annual_period': period,
            'scope': 'Evidence collection priority only; not investment ranking or backtest approval',
            'candidate_count': len(reminders), 'general_enterprises': len(companies),
            'blocked_gates': dict(Counter(c['name'] for r in reminders
                                         for c in r['decision_checks'] if not c['passed'])),
            'annual_field_gaps': dict(totals),
            'collection_priority': sorted(companies, key=lambda r: (r['gap_count'], r['symbol']))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=Path)
    parser.add_argument('--period', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = audit(json.loads(args.payload.read_text(encoding='utf-8-sig')), args.period)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({**result, 'collection_priority': result['collection_priority'][:10]},
                     ensure_ascii=False, indent=2))
