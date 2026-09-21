"""Retain distinct ROE observations and hash-addressed structured snapshots."""
import hashlib
import json
import argparse
from dataclasses import replace
from value_investment_agent.adapters import SinaFinancialAdapter
from value_investment_agent.db import connect, begin_run, end_run, store_record
from value_investment_agent.settings import get_settings

settings = get_settings()
parser = argparse.ArgumentParser()
parser.add_argument('--limit', type=int, default=15)
parser.add_argument('--symbols', nargs='+', help='Explicit six-digit stock codes; at most 20.')
parser.add_argument('--fields', nargs='+', choices=[
    'roe_simple', 'roe_weighted', 'provider_sales_net_margin',
    'main_business_revenue_yoy', 'provider_net_income_yoy',
    'provider_cashflow_profit_ratio'], default=['roe_simple', 'roe_weighted'])
args = parser.parse_args()
if not 1 <= args.limit <= 20:
    parser.error('limit must be between 1 and 20')
if args.symbols and (len(args.symbols) > 20 or any(
        len(s) != 6 or not s.isascii() or not s.isdigit() for s in args.symbols)):
    parser.error('symbols must contain at most 20 six-digit stock codes')
with connect(settings.database_url) as db:
    symbols = list(dict.fromkeys(args.symbols)) if args.symbols else [r['symbol'] for r in db.execute("""WITH latest AS (
        SELECT DISTINCT ON(symbol,period_label) * FROM data_points
        WHERE field_name='roe' AND NOT (metadata ? 'superseded_by_parser')
        ORDER BY symbol,period_label,created_at DESC,data_point_id DESC
    ) SELECT DISTINCT p.symbol FROM latest p JOIN raw_documents d ON d.document_id=p.source_id
      WHERE p.validation_status='pending' AND p.period_label ~ '^[0-9]{4}-12-31$'
        AND d.source_name='AkShare / Sina financial indicators'
        AND EXISTS (SELECT 1 FROM data_points v WHERE v.symbol=p.symbol
            AND v.field_name='roe' AND v.period_label=p.period_label
            AND v.validation_status='verified' AND NOT (v.metadata ? 'evidence_quarantine')
            AND NOT (v.metadata ? 'superseded_by_parser'))
      ORDER BY p.symbol LIMIT %s""",(args.limit,)).fetchall()]
archive = settings.evidence_directory / 'roe-secondary'
archive.mkdir(parents=True, exist_ok=True)
for symbol in symbols:
    records = [r for r in SinaFinancialAdapter().fetch([symbol])
               if r.field_name in args.fields]
    if not records:
        raise ValueError('No selected indicator evidence: ' + symbol)
    retained = []
    for record in records:
        digest = hashlib.sha256(record.raw_payload).hexdigest()
        path = archive / (digest + '.json')
        if not path.exists():
            with path.open('xb') as stream:
                stream.write(record.raw_payload)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Archived snapshot hash mismatch')
        retained.append(replace(record, local_path=str(path)))
    with connect(settings.database_url) as db:
        db.execute("SET lock_timeout='5s'")
        db.execute("SET statement_timeout='30s'")
        run = begin_run(db, 'collect-roe-evidence')
        # Compare point-level facts, not shared raw-document parser metadata.
        protected_sql = """SELECT data_point_id,field_name,period_label,value,unit,
            validation_status,metadata FROM data_points WHERE symbol=%s
            AND field_name IN ('roe','net_margin','revenue_yoy','net_income_yoy',
                'operating_cash_flow_to_net_income') ORDER BY data_point_id"""
        before = db.execute(protected_sql, (symbol,)).fetchall()
        recovered = set()
        for record in retained:
            digest = hashlib.sha256(record.raw_payload).hexdigest()
            old = db.execute("""SELECT document_id FROM raw_documents WHERE sha256=%s
                AND (local_path IS NULL OR local_path='')""", (digest,)).fetchone()
            store_record(db, record, 'pending')
            if old:
                db.execute('UPDATE raw_documents SET local_path=%s WHERE document_id=%s AND sha256=%s',
                           (record.local_path, old['document_id'], digest))
                recovered.add(str(old['document_id']))
        if before != db.execute(protected_sql, (symbol,)).fetchall():
            raise ValueError('Canonical observations changed during supplemental collection')
        result = {'symbol':symbol,'requested_fields':args.fields,
            'canonical_observations_unchanged':True,'canonical_observations_checked':len(before),'records':[
            {'field':r.field_name,'period':r.period_label,'value':str(r.value),
             'metadata':r.point_metadata,'sha256':hashlib.sha256(r.raw_payload).hexdigest()}
            for r in retained], 'recovered_historical_snapshots':sorted(recovered),
            'validation_status':'pending'}
        end_run(db,run,'succeeded',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
