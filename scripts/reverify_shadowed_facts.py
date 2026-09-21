"""Reverify exact matching monetary facts against original PDFs; default rollback."""
import argparse
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from decimal import Decimal
from value_investment_agent.filing_extract import extract_candidates_from_pages
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.candidate_review import latest_consistent_secondary, cashflow_secondary
from value_investment_agent.db import connect,begin_run,end_run,store_record
from value_investment_agent.models import SourceRecord
from value_investment_agent.settings import get_settings

parser = argparse.ArgumentParser()
parser.add_argument('--apply',action='store_true')
parser.add_argument('--limit', type=int, default=10)
parser.add_argument('--cash-only', action='store_true')
parser.add_argument('--symbols', nargs='+', default=['000709','000830','000858','000887','000928'])
args = parser.parse_args()
if not 1 <= args.limit <= 20:
    parser.error('limit must be between 1 and 20')
if len(args.symbols)>20 or any(len(s)!=6 or not s.isascii() or not s.isdigit() for s in args.symbols):
    parser.error('Provide at most 20 six-digit symbols')
with connect(get_settings().database_url) as db:
    db.execute("SET lock_timeout='5s'")
    db.execute("SET statement_timeout='60s'")
    db.execute('LOCK TABLE data_points IN SHARE ROW EXCLUSIVE MODE')
    def fact_snapshot():
        return sorted(json.dumps(r, default=str, sort_keys=True) for r in db.execute(
            'SELECT * FROM data_points WHERE symbol=ANY(%s)', (args.symbols,)).fetchall())
    before = fact_snapshot()
    rows = db.execute("""WITH latest AS (
        SELECT DISTINCT ON (symbol,field_name,period_label) *,
            count(*) OVER (PARTITION BY symbol,field_name,period_label,created_at) AS time_ties
        FROM data_points
        WHERE symbol=ANY(%s) AND NOT (metadata ? 'superseded_by_parser')
        ORDER BY symbol,field_name,period_label,created_at DESC,data_point_id DESC
    ), scoped AS (
        SELECT DISTINCT ON (p.symbol,p.field_name,p.period_label) p.*
        FROM data_points p JOIN raw_documents d ON d.document_id=p.source_id
        WHERE p.symbol=ANY(%s) AND NOT (p.metadata ? 'superseded_by_parser')
          AND NOT (p.metadata ? 'evidence_quarantine')
          AND ((p.field_name='net_income' AND d.source_name='AkShare / Sina financial abstract')
            OR (d.source_name='AkShare / Sina detailed financial statements'
                AND p.metadata->>'statement_scope'='consolidated'))
        ORDER BY p.symbol,p.field_name,p.period_label,p.created_at DESC,p.data_point_id DESC
    ) SELECT DISTINCT ON (p.data_point_id) p.data_point_id AS secondary_id,p.source_id AS secondary_source_id,
        trigger.data_point_id AS trigger_id, trigger.value AS trigger_value, trigger.unit AS trigger_unit,
        p.symbol,p.field_name,p.period_label,p.value,p.unit,d.source_name AS secondary_name,
        d.source_url AS secondary_url,v.data_point_id AS previous_verified_id,
        c.candidate_id,c.page_number,c.source_label,o.source_name,o.source_url,o.sha256,o.local_path,o.published_at
      FROM scoped p JOIN raw_documents d ON d.document_id=p.source_id
      JOIN latest trigger ON trigger.symbol=p.symbol AND trigger.field_name=p.field_name
        AND trigger.period_label=p.period_label AND trigger.time_ties=1
        AND ((trigger.value=p.value AND trigger.unit=p.unit)
          OR (trigger.source_id=p.source_id AND p.field_name='cash' AND p.unit='CNY'
            AND trigger.unit IN ('CNY 10K','CNY 100M')
            AND trigger.value * CASE trigger.unit WHEN 'CNY 10K' THEN 10000
                WHEN 'CNY 100M' THEN 100000000 END = p.value))
        AND trigger.validation_status='pending' AND NOT (trigger.metadata ? 'evidence_quarantine')
      JOIN data_points v ON v.symbol=p.symbol AND v.field_name=p.field_name AND v.period_label=p.period_label
        AND v.value=p.value AND v.unit=p.unit AND v.validation_status='verified'
        AND v.metadata->>'automatic_cross_source_verification'='true'
        AND NOT (v.metadata ? 'evidence_quarantine') AND NOT (v.metadata ? 'superseded_by_parser')
      JOIN filing_candidates c ON c.candidate_id::text=v.metadata->>'candidate_id'
      JOIN official_disclosures o ON o.disclosure_id=c.disclosure_id
      WHERE p.validation_status='pending' AND p.unit='CNY'
        AND p.period_label ~ '^[0-9]{4}-12-31$'
        AND NOT EXISTS (SELECT 1 FROM data_points other
            WHERE other.symbol=p.symbol AND other.field_name=p.field_name AND other.period_label=p.period_label
              AND other.validation_status='verified'
              AND NOT (other.metadata ? 'evidence_quarantine')
              AND NOT (other.metadata ? 'superseded_by_parser')
              AND (other.value<>p.value OR other.unit<>p.unit))
        AND NOT (p.metadata ? 'evidence_quarantine')
        AND c.status='automatically_verified'
        AND (d.source_name<>'AkShare / Sina detailed financial statements'
             OR p.metadata->>'statement_scope'='consolidated')
        AND c.value=p.value AND c.unit=p.unit AND c.field_name=p.field_name
        AND o.symbol=p.symbol AND o.report_period=p.period_label AND o.source_url<>d.source_url
        AND ((p.field_name='net_income' AND d.source_name='AkShare / Sina financial abstract')
          OR (p.field_name IN ('revenue','operating_cost','cash','operating_cash_flow','total_assets',
              'total_liabilities','short_term_borrowings','current_portion_long_term_debt',
              'long_term_borrowings','bonds_payable')
              AND d.source_name='AkShare / Sina detailed financial statements'))
      ORDER BY p.data_point_id,v.created_at DESC LIMIT %s""", (args.symbols,args.symbols,args.limit)).fetchall()
    if args.cash_only:
        rows = [row for row in rows if row['field_name'] == 'cash']
    run = begin_run(db,'reverify-shadowed-official-facts')
    restored = []
    skipped = []
    parsed = {}
    for row in rows:
        payload = Path(row['local_path']).read_bytes()
        if hashlib.sha256(payload).hexdigest() != row['sha256']:
            raise ValueError('Official PDF hash mismatch: '+row['symbol'])
        if row['sha256'] not in parsed:
            parsed[row['sha256']] = extract_candidates_from_pages(extract_pages(Path(row['local_path'])))
        agrees = any(c['field_name']==row['field_name'] and Decimal(c['value'])==row['value']
            and c['unit']==row['unit'] and c['page']==row['page_number']
            and c['source_label']==row['source_label'] for c in parsed[row['sha256']])
        matches = db.execute("""SELECT p.data_point_id,p.value,p.unit,d.source_name,p.metadata
            FROM data_points p JOIN raw_documents d ON d.document_id=p.source_id
            WHERE p.symbol=%s AND p.field_name=%s AND p.period_label=%s AND d.source_url<>%s
              AND p.validation_status IN ('pending','verified')
              AND NOT (p.metadata ? 'evidence_quarantine')
              AND NOT (p.metadata ? 'superseded_by_parser')
            ORDER BY p.created_at DESC,p.data_point_id DESC""",
            (row['symbol'],row['field_name'],row['period_label'],row['source_url'])).fetchall()
        sources_agree = latest_consistent_secondary(matches,row['value'],row['unit']) is not None
        if row['field_name'] == 'operating_cash_flow':
            selected = cashflow_secondary(matches, row['value'], row['unit'])
            sources_agree = selected is not None and selected['data_point_id'] == row['secondary_id']
        if not agrees or not sources_agree:
            skipped.append({'symbol':row['symbol'],'field':row['field_name'],
                'reason':'current_parser_or_latest_source_disagreement',
                'current_parser_agrees':agrees,'latest_sources_agree':sources_agree,
                'previous_page':row['page_number'],'previous_value':str(row['value']),
                'current_candidates':[{'value':c['value'],'page':c['page'],'label':c['source_label']}
                    for c in parsed[row['sha256']] if c['field_name']==row['field_name']]})
            continue
        metadata = {'automatic_cross_source_verification':True,
            'verification_method':'official_pdf_plus_independent_structured_source',
            'candidate_id':str(row['candidate_id']),'page_number':row['page_number'],
            'source_label':row['source_label'],'official_file_sha256':row['sha256'],
            'official_file_hash_verified_at_promotion':True,
            'secondary_data_point_id':str(row['secondary_id']),
            'secondary_source_id':str(row['secondary_source_id']),
            'secondary_source_name':row['secondary_name'],'secondary_source_url':row['secondary_url'],
            'reverification':{'reason':'exact_latest_secondary_matches_original_pdf_candidate',
                'trigger_data_point_id':str(row['trigger_id']),
                'trigger_original_value':str(row['trigger_value']),
                'trigger_original_unit':row['trigger_unit'],
                'normalized_value':str(row['value']), 'normalized_unit':row['unit'],
                'previous_data_point_ids':[str(row['previous_verified_id'])],
                'previous_records_preserved':True,'run_id':str(run)}}
        record = SourceRecord(row['symbol'],row['field_name'],row['period_label'],row['value'],row['unit'],
            row['source_name'],row['source_url'],row['published_at'],datetime.now(timezone.utc),
            'official-shadow-reverification-v3-latest-cashflow-scope',payload,row['local_path'],metadata)
        store_record(db,record,'verified',False)
        restored.append({'symbol':row['symbol'],'field':row['field_name'],'period':row['period_label']})
    result = {'records':len(restored),'facts':restored,'skipped':skipped,'applied':args.apply}
    end_run(db,run,'succeeded',result)
    if not args.apply:
        db.rollback()
        if fact_snapshot() != before or db.execute('SELECT 1 FROM task_runs WHERE run_id=%s', (run,)).fetchone():
            raise ValueError('Rollback readback failed')
        result['rollback_verified'] = True
print(json.dumps(result))
