"""Read-only debt-component coverage across the current general-company pool."""
import json
from collections import Counter

from value_investment_agent.db import connect, latest_points
from value_investment_agent.settings import get_settings


FIELDS = ('short_term_borrowings', 'current_portion_long_term_debt',
          'long_term_borrowings', 'bonds_payable')


def main():
    with connect(get_settings().database_url) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        db.execute("SET statement_timeout='45s'")
        pool = db.execute("""SELECT m.symbol, i.name, q.coverage_ratio
            FROM market_screen_results m JOIN instruments i USING (symbol)
            JOIN financial_quality_results q USING (symbol)
            WHERE m.screen_date=(SELECT max(screen_date) FROM market_screen_results)
              AND q.model_type='general_enterprise'""").fetchall()
        symbols = {row['symbol'] for row in pool}
        points = {(p['symbol'], p['field_name']): p
                  for p in latest_points(db, annual_only=True)
                  if p['symbol'] in symbols and p['field_name'] in FIELDS}
        reports = db.execute("""SELECT DISTINCT ON (symbol) symbol, report_period,
                extraction_status, extraction_parser_version, source_url
            FROM official_disclosures WHERE symbol=ANY(%s) AND report_kind='annual'
            ORDER BY symbol, report_period DESC, published_at DESC""", (list(symbols),)).fetchall()
    reports = {r['symbol']: r for r in reports}
    counts = {field: Counter() for field in FIELDS}
    numeric_pending = []
    for company in pool:
        report = reports.get(company['symbol'])
        pending = []
        verified = 0
        for field in FIELDS:
            point = points.get((company['symbol'], field))
            meta = (point or {}).get('metadata') or {}
            if not point:
                state = 'missing_numeric'
            elif not report or point['period_label'] != report['report_period']:
                state = 'period_mismatch_or_no_annual'
            elif meta.get('evidence_quarantine'):
                state = 'quarantined'
            elif point['validation_status'] == 'verified' and meta.get('automatic_cross_source_verification'):
                state = 'verified'
                verified += 1
            else:
                state = ('verified_without_independent_evidence'
                         if point['validation_status'] == 'verified' else point['validation_status'])
                if state == 'pending':
                    pending.append({'field': field, 'value': str(point['value']),
                                    'source_name': point['source_name']})
            counts[field][state] += 1
        if pending:
            numeric_pending.append({**company, 'verified_components': verified,
                                    'pending_numeric': pending, 'report': report})
    numeric_pending.sort(key=lambda r: (-r['verified_components'], -r['coverage_ratio'], r['symbol']))
    print(json.dumps({'read_only': True, 'general_companies': len(pool),
                      'component_states': counts,
                      'companies_with_pending_numeric': len(numeric_pending),
                      'prioritized_first_30': numeric_pending[:30],
                      'scope_note': 'Missing numeric is unknown, never zero. Four components are not exhaustive debt.'},
                     ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
