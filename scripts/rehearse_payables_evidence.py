"""Exercise retained components against official PDFs, always rolling back SQL."""
import hashlib
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

from value_investment_agent.db import connect, store_record
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.settings import get_settings


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapters = load('value_investment_agent.payables_adapters', 'payables_adapters.py')
parser = load('payables_parser', 'payables_parser.py')
gate = load('payables_evidence', 'payables_evidence.py')
field = 'long_term_payables_noncurrent'
settings = get_settings()
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
    official = [c for c in parser.extract_candidates_from_pages(extract_pages(path))
                if c['field_name'] == field]
    records = [r for r in adapters.SinaFinancialStatementsAdapter().fetch(
        [symbol], report_period=report['report_period'])
        if r.symbol == symbol and r.period_label == report['report_period']
        and r.field_name in (*gate.FIELDS, field)]
    results = []
    with connect(settings.database_url) as db:
        try:
            db.execute("SET lock_timeout='5s'")
            db.execute("SET statement_timeout='30s'")
            for record in records:
                first = store_record(db, record)
                if store_record(db, record) != first:
                    raise ValueError('Repeated collection did not deduplicate')
            matches = db.execute("""SELECT p.*,d.source_name,d.sha256 FROM data_points p
                JOIN raw_documents d ON d.document_id=p.source_id
                WHERE p.symbol=%s AND p.period_label=%s AND p.field_name=%s
                ORDER BY p.created_at DESC""", (symbol, report['report_period'], field)).fetchall()
            for match in matches:
                inputs = db.execute("""SELECT * FROM data_points WHERE source_id=%s
                    AND symbol=%s AND period_label=%s AND field_name=ANY(%s)""",
                    (match['source_id'], symbol, report['report_period'], list(gate.FIELDS))).fetchall()
                valid = gate.validate_payables_components(match, inputs, symbol, report['report_period'])
                corroborated = valid and any(Decimal(c['value']) == match['value'] and c['unit'] == match['unit']
                                            for c in official)
                results.append({'valid_components': valid, 'official_agrees': corroborated,
                    'value': str(match['value']), 'input_count': len(inputs),
                    'raw_sha256': match['sha256']})
            if symbol == '000338' and not any(r['official_agrees'] for r in results):
                raise ValueError('Complete sample failed corroboration')
            if symbol == '000683' and any(r.field_name == field for r in records):
                raise ValueError('Missing special component was treated as zero')
        finally:
            db.rollback()
    print(json.dumps({'symbol': symbol, 'period': report['report_period'],
        'official_url': report['source_url'], 'official_sha256': report['sha256'],
        'official_candidates': official, 'retained_rehearsal': results,
        'collected_fields': [r.field_name for r in records], 'sql_rolled_back': True}, default=str), flush=True)
