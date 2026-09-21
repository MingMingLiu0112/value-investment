"""Retain bounded same-period payables evidence; never classify it as financing debt."""
import hashlib
import json
import uuid
from dataclasses import replace

from value_investment_agent.adapters import SinaFinancialStatementsAdapter
from value_investment_agent.db import connect, begin_run, end_run, store_record
from value_investment_agent.filing_extract import extract_candidates_from_pages, ANNUAL_BACKFILL_PARSER_VERSION
from value_investment_agent.payables_evidence import FIELDS
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.settings import get_settings
from pathlib import Path

settings = get_settings()
field = 'long_term_payables_noncurrent'
for symbol in ('000338', '000683'):
    with connect(settings.database_url) as db:
        report = db.execute("""SELECT * FROM official_disclosures WHERE symbol=%s
            AND report_kind='annual' ORDER BY report_period DESC,published_at DESC LIMIT 1""",
            (symbol,)).fetchone()
    if not report:
        raise ValueError('Missing official report: ' + symbol)
    path = Path(report['local_path'])
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != report['sha256']:
            raise ValueError('Official PDF hash mismatch')
    candidates = [c for c in extract_candidates_from_pages(extract_pages(path)) if c['field_name'] == field]
    records = [r for r in SinaFinancialStatementsAdapter().fetch([symbol], report_period=report['report_period'])
        if r.symbol == symbol and r.period_label == report['report_period'] and r.field_name in (*FIELDS, field)]
    archive = settings.evidence_directory / 'payables-secondary'
    archive.mkdir(parents=True, exist_ok=True)
    retained = []
    for record in records:
        digest = hashlib.sha256(record.raw_payload).hexdigest()
        target = archive / (digest + '.json')
        if not target.exists():
            with target.open('xb') as stream:
                stream.write(record.raw_payload)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError('Structured snapshot archive hash mismatch')
        retained.append(replace(record, local_path=str(target)))
    with connect(settings.database_url) as db:
        run = begin_run(db, 'collect-payables-samples')
        for record in retained:
            store_record(db, record, 'pending')
            db.execute("""UPDATE raw_documents SET local_path=%s
                WHERE sha256=%s AND (local_path IS NULL OR local_path='')""",
                (record.local_path, hashlib.sha256(record.raw_payload).hexdigest()))
        for c in candidates:
            db.execute("""INSERT INTO filing_candidates(candidate_id,disclosure_id,field_name,value,unit,
                page_number,source_label,excerpt,parser_version,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (disclosure_id,field_name,page_number,source_label) DO NOTHING""",
                (uuid.uuid4(), report['disclosure_id'], field, c['value'], c['unit'], c['page'],
                 c['source_label'], c['excerpt'], ANNUAL_BACKFILL_PARSER_VERSION, c['status']))
        result = {'symbol': symbol, 'period': report['report_period'], 'stored': len(retained),
            'fields': [r.field_name for r in retained], 'official_candidates': len(candidates),
            'official_sha256': report['sha256'], 'financing_classification': 'not_assessed'}
        end_run(db, run, 'succeeded', result)
    print(json.dumps(result), flush=True)
