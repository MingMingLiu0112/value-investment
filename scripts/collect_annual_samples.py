"""Bounded exact-period backfill; official evidence remains mandatory for promotion."""
import json
import argparse
import hashlib
from dataclasses import replace
from value_investment_agent.adapters import AkshareFinancialAbstractAdapter, SinaFinancialStatementsAdapter
from value_investment_agent.db import connect, begin_run, end_run, store_record
from value_investment_agent.settings import get_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbols', nargs='+', default=['000333','600036','600519'])
    parser.add_argument('--statement-fields', nargs='+',
                        choices=['operating_cash_flow','long_term_borrowings'])
    args = parser.parse_args()
    if len(args.symbols) > 20 or any(len(s) != 6 or not s.isascii() or not s.isdigit() for s in args.symbols):
        parser.error('Provide at most 20 six-digit symbols')
    with connect(get_settings().database_url) as db:
        rows = db.execute("""SELECT DISTINCT ON (symbol) symbol,report_period
            FROM official_disclosures WHERE symbol=ANY(%s) AND report_kind='annual'
            ORDER BY symbol,report_period DESC,published_at DESC""",
            (args.symbols,)).fetchall()
    settings = get_settings()
    archive = settings.evidence_directory / 'annual-secondary'
    archive.mkdir(parents=True, exist_ok=True)
    for row in rows:
        records = [] if args.statement_fields else AkshareFinancialAbstractAdapter().fetch(
            [row['symbol']],report_period=row['report_period'])
        records += SinaFinancialStatementsAdapter().fetch([row['symbol']], report_period=row['report_period'])
        records = [r for r in records if r.symbol==row['symbol'] and r.period_label==row['report_period']
                   and (not args.statement_fields or (r.field_name in args.statement_fields
                        and (r.point_metadata or {}).get('statement_scope')=='consolidated'
                        and r.unit=='CNY'))]
        retained = []
        for record in records:
            digest = hashlib.sha256(record.raw_payload).hexdigest()
            path = archive / (digest + '.json')
            if not path.exists():
                with path.open('xb') as stream:
                    stream.write(record.raw_payload)
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('Structured archive hash mismatch')
            retained.append(replace(record,local_path=str(path)))
        with connect(get_settings().database_url) as db:
            run = begin_run(db,'annual-sample-backfill')
            for record in retained:
                store_record(db,record,'pending')
                db.execute("""UPDATE raw_documents SET local_path=%s WHERE sha256=%s
                    AND (local_path IS NULL OR local_path='')""",
                    (record.local_path,hashlib.sha256(record.raw_payload).hexdigest()))
            result = {**row,'stored':len(records),'fields':sorted({r.field_name for r in records})}
            end_run(db,run,'succeeded',result)
        print(json.dumps(result),flush=True)


if __name__ == '__main__':
    main()
