"""Quarantine proven summary parsing defects, preserving candidate and fact values."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from value_investment_agent.db import connect, begin_run, end_run, latest_points, upsert_valuation
from value_investment_agent.cli import _refresh_financial_quality, as_valuation_row
from value_investment_agent.quality import evaluate
from evidence_dependencies import affected_point_ids
from value_investment_agent.filing_extract import extract_candidates_from_pages
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.settings import get_settings

parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true')
mode = parser.add_mutually_exclusive_group()
mode.add_argument('--summary-688087', action='store_true')
mode.add_argument('--bank-lease-000001', action='store_true')
args = parser.parse_args()
expected = {
    '600057': 'c48dfe8909030d4b19b43ee4e7ed367e7619cd65e77607090edeccdff4a61386',
    '600479': '6831f115fec8359a05f20a6b86143aea08e80397442cb9166bb16e66956031d2',
}
summary_page = 7
if args.bank_lease_000001:
    expected = {'000001': '2273565ecbe1b32536631fd4a019a4f4a990f4c793cfd5b70eae90d44d3ff16c'}
if args.summary_688087:
    from filing_extract import extract_candidates_from_pages
    expected = {'688087': 'd5ea80d0a678586b178bb95bdedcabd00459fd23c98ea5601d772ec55adfaa9a'}
    summary_page = 14
settings = get_settings()
with connect(settings.database_url) as db:
    reports = db.execute('SELECT * FROM official_disclosures WHERE symbol=ANY(%s) AND sha256=ANY(%s)',
                         (list(expected), list(expected.values()))).fetchall()
parsed = {}
for report in reports:
    path = Path(report['local_path'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected[report['symbol']]:
        raise ValueError('Official PDF hash mismatch')
    parsed[str(report['disclosure_id'])] = extract_candidates_from_pages(extract_pages(path))
if len(parsed) != len(expected):
    raise ValueError('All expected official reports are required')
if args.summary_688087:
    corrected = {r['field_name']:r['value'] for rows in parsed.values() for r in rows if r['page']==14}
    for field, amount in {'revenue':'3546216993.66','net_income':'285734507.57',
                          'operating_cash_flow':'568565377.28'}.items():
        assert Decimal(corrected[field]) == Decimal(amount), 'Corrected official amount not reproduced'
with connect(settings.database_url) as db:
    db.execute("SET lock_timeout='5s'")
    db.execute("SET statement_timeout='60s'")
    db.execute('LOCK TABLE filing_candidates, data_points IN SHARE ROW EXCLUSIVE MODE')
    if args.bank_lease_000001:
        candidates = db.execute("""SELECT * FROM filing_candidates
            WHERE candidate_id='9e0cf57f-de1b-4a21-ab9f-72185b8a7c39'
              AND disclosure_id::text=ANY(%s)""", (list(parsed),)).fetchall()
        if len(candidates) != 1:
            raise ValueError('Expected audited bank lease candidate missing')
        candidate = candidates[0]
        assert candidate['field_name'] == 'lease_liabilities_noncurrent'
        assert candidate['value'] == Decimal('4255000000')
        assert candidate['page_number'] == 33 and candidate['unit'] == 'CNY'
    else:
        candidates = db.execute("""SELECT * FROM filing_candidates
        WHERE disclosure_id::text=ANY(%s) AND page_number=%s
          AND field_name IN ('revenue','net_income','operating_cash_flow')
          AND status<>'superseded_by_parser'""", (list(parsed),summary_page)).fetchall()
    obsolete = [c for c in candidates if args.bank_lease_000001 or not any(
        n['field_name'] == c['field_name'] and n['page'] == c['page_number']
        and n['source_label'] == c['source_label'] and Decimal(n['value']) == c['value']
        and n['unit'] == c['unit'] for n in parsed[str(c['disclosure_id'])])]
    ids = [str(c['candidate_id']) for c in obsolete]
    rows = db.execute("""SELECT data_point_id,symbol,field_name,period_label,source_id,
        validation_status,metadata FROM data_points
        WHERE metadata ? 'candidate_id' OR metadata ? 'secondary_data_point_id'
          OR metadata ? 'input_source_ids' OR metadata ? 'input_facts'
          OR metadata ? 'input_data_point_ids'""").fetchall()
    initial = [p['data_point_id'] for p in rows if p['metadata'].get('candidate_id') in ids]
    affected = affected_point_ids(rows, initial)
    selected = [p for p in rows if str(p['data_point_id']) in affected and not p['metadata'].get('evidence_quarantine')]
    run = begin_run(db, 'quarantine-proven-summary-parsing-defects')
    for point in selected:
        metadata = dict(point['metadata'])
        metadata['evidence_quarantine'] = {'reason': (
            'total_bank_lease_liabilities_not_noncurrent_scope' if args.bank_lease_000001
            else 'proven_summary_period_or_amount_fragment_error'),
            'run_id': str(run), 'at': datetime.now(timezone.utc).isoformat(),
            'previous_validation_status': point['validation_status'], 'previous_metadata': point['metadata']}
        metadata['automatic_cross_source_verification'] = False
        db.execute("UPDATE data_points SET validation_status='failed',metadata=%s WHERE data_point_id=%s",
                   (json.dumps(metadata), point['data_point_id']))
    if ids:
        db.execute("UPDATE filing_candidates SET status='superseded_by_parser' WHERE candidate_id::text=ANY(%s)", (ids,))
    symbols = sorted({p['symbol'] for p in selected})
    if symbols:
        grouped = {s: [] for s in symbols}
        for point in latest_points(db):
            if point['symbol'] in grouped:
                grouped[point['symbol']].append(point)
        for symbol, points in grouped.items():
            verdict = evaluate(symbol, points, settings.data_max_age_hours, Decimal(str(settings.price_conflict_tolerance)))
            upsert_valuation(db, as_valuation_row(verdict))
        _refresh_financial_quality(db, symbols)
    result = {'candidates': len(obsolete), 'points': len(selected), 'symbols': symbols, 'applied': args.apply}
    end_run(db, run, 'succeeded', {**result, 'previous_candidates': json.loads(json.dumps(obsolete, default=str)),
        'previous_points': json.loads(json.dumps(selected, default=str)), 'official_hashes': expected})
    if not args.apply:
        db.rollback()
print(json.dumps(result))
