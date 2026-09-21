"""Explain specialised Excel gaps from the exact exported evidence, not guesses."""
import argparse
from collections import Counter
import json
from pathlib import Path

from value_investment_agent.excel_report import choose_points, SPECIAL_FIELDS, GENERAL, number, accepted
from value_investment_agent.financial_institutions import provisional_financial_type
from value_investment_agent.candidate_tracking import tracking_candidate_view


def audit(payload):
    points = choose_points(payload.get('points', []))
    disclosures = {str(d['symbol']).zfill(6): d for d in payload.get('disclosures', [])}
    relevant = set(GENERAL) | {'revenue', 'net_income', 'bvps'} | {
        f for fs in SPECIAL_FIELDS.values() for f in fs}
    rows = []
    for company in tracking_candidate_view(payload):
        model = provisional_financial_type(company.get('name'), company.get('sector'))
        if model not in SPECIAL_FIELDS:
            continue
        symbol = str(company['symbol']).zfill(6)
        period = max((str(p['period_label']) for (s, f), p in points.items()
                      if s == symbol and f in relevant),
                     default=str(disclosures.get(symbol, {}).get('report_period', '')))
        disclosure = disclosures.get(symbol, {})
        for field in SPECIAL_FIELDS[model]:
            p = points.get((symbol, field))
            same_period = p is not None and str(p['period_label']) == period
            visible = same_period and number(p.get('value')) is not None and p.get('validation_status') not in {'failed', 'conflict'}
            status = ('value_verified' if accepted(p) else 'value_unverified') if visible else (
                'older_or_other_period' if p and not same_period else
                'failed_or_nonnumeric' if p else
                'no_point_with_matching_disclosure' if str(disclosure.get('report_period', '')) == period else
                'no_point_no_matching_disclosure')
            rows.append({'symbol': symbol, 'name': company['name'], 'model': model,
                         'field': field, 'required_period': period, 'status': status,
                         'point_period': p.get('period_label') if p else None,
                         'source_id': p.get('source_id') if p else None,
                         'disclosure_url': disclosure.get('source_url'),
                         'disclosure_period': disclosure.get('report_period')})
    return {'generated_at': payload['generated_at'], 'required': len(rows),
            'status_counts': dict(Counter(r['status'] for r in rows)),
            'limitation': 'Exported disclosure presence does not prove archived PDF availability or parser failure',
            'rows': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = audit(json.loads(args.payload.read_text(encoding='utf-8-sig')))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, ensure_ascii=False))
