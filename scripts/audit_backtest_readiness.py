"""Inventory exported evidence; never infer historical backtest readiness."""
import argparse
import json
from collections import Counter
from pathlib import Path


def audit(payload):
    results = []
    for symbol in ('600519', '000333', '601088'):
        points = [p for p in payload.get('points', []) + payload.get('annual_points', [])
                  if p['symbol'] == symbol]
        unique = {(p.get('source_id'), p['field_name'], p.get('period_label')): p for p in points}
        rows = list(unique.values())
        fair = [p for p in rows if p['field_name'] == 'fair_value']
        verified = [p for p in fair if p.get('validation_status') == 'verified'
                    and (p.get('metadata') or {}).get('automatic_cross_source_verification') is True
                    and not (p.get('metadata') or {}).get('evidence_quarantine')]
        results.append({'symbol': symbol, 'unique_evidence_rows': len(rows),
            'periods': sorted({str(p.get('period_label')) for p in rows}),
            'fields': dict(Counter(p['field_name'] for p in rows)),
            'rows_with_publication_time': sum(bool(p.get('published_at')) for p in rows),
            'verified_fair_values': len(verified),
            'historical_backtest_ready': False,
            'limitations': ['Latest export is not a point-in-time historical database',
                'Historical daily execution prices and corporate actions not audited',
                'Historical valuation input availability and revision lineage not audited',
                'Historical trading constraints and transaction costs not audited']})
    return {'export_generated_at': payload.get('generated_at'),
            'scope': 'Export inventory only; no performance results or strategy approval',
            'companies': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(json.loads(args.payload.read_text(encoding='utf-8'))),
                     ensure_ascii=False, indent=2))
