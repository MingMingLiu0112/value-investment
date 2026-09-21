"""Bounded collection of retained same-scope annual growth cross-checks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .adapters import AkshareFinancialAbstractAdapter, SinaFinancialStatementsAdapter
from .db import begin_run, connect, end_run, record_failed_run, store_record
from .growth_evidence import SOURCES, build_growth_evidence, official_growth_period_matches
from .settings import get_settings

TASK = 'collect-growth-evidence-symbol'
LOCK = 746192803


def collect_inputs(symbol, period, fields):
    previous = f'{int(period[:4]) - 1}-12-31'
    periods = {}
    for requested in (period, previous):
        records = []
        if 'revenue' in fields:
            records.extend(SinaFinancialStatementsAdapter().fetch([symbol], report_period=requested))
        if 'net_income' in fields:
            records.extend(AkshareFinancialAbstractAdapter().fetch([symbol], report_period=requested))
        selected = {}
        for field in fields:
            matches = [r for r in records if r.symbol == symbol and r.period_label == requested
                       and r.field_name == field and r.source_name == SOURCES[field] and r.unit == 'CNY']
            if not matches or len({r.value for r in matches}) != 1:
                raise ValueError(f'Missing or conflicting same-scope input: {symbol}/{requested}/{field}')
            selected[field] = matches[0]
        periods[requested] = selected
    return {field: (periods[period][field], periods[previous][field]) for field in fields}


def select_reports(db, limit):
    rows = db.execute("""SELECT o.disclosure_id,o.symbol,o.report_period,o.local_path,o.sha256,
            c.field_name,c.excerpt
        FROM official_disclosures o JOIN filing_candidates c USING (disclosure_id)
        JOIN market_screen_results m ON m.symbol=o.symbol
          AND m.screen_date=(SELECT max(screen_date) FROM market_screen_results)
        LEFT JOIN financial_quality_results q ON q.symbol=o.symbol
        WHERE o.archive_status='server_resident'
          AND o.report_kind='annual' AND c.field_name IN ('revenue_yoy','net_income_yoy')
          AND c.status <> 'superseded_by_parser'
          AND o.disclosure_id=(SELECT latest.disclosure_id FROM official_disclosures latest
              WHERE latest.symbol=o.symbol AND latest.report_kind='annual'
              ORDER BY latest.report_period DESC,latest.published_at DESC LIMIT 1)
          AND NOT EXISTS (SELECT 1 FROM data_points p
              WHERE p.metadata->>'candidate_id'=c.candidate_id::text
                AND p.validation_status='verified'
                AND NOT (p.metadata ? 'evidence_quarantine')
                AND NOT (p.metadata ? 'superseded_by_parser'))
          AND NOT EXISTS (SELECT 1 FROM task_runs t WHERE t.task_name=%s
              AND t.details->>'symbol'=o.symbol AND t.details->>'period'=o.report_period
              AND t.started_at > now()-interval '6 hours')
        ORDER BY q.coverage_ratio DESC NULLS LAST,o.symbol,c.field_name""", (TASK,)).fetchall()
    selected = {}
    for row in rows:
        if not official_growth_period_matches(row['excerpt'], row['report_period']):
            continue
        key = row['disclosure_id']
        if key not in selected:
            if len(selected) >= limit:
                continue
            selected[key] = {**row, 'fields': set()}
        selected[key]['fields'].add(row['field_name'].removesuffix('_yoy'))
    return list(selected.values())


def collect_growth_evidence(limit=5):
    if not 1 <= limit <= 20:
        raise ValueError('limit must be between 1 and 20')
    result = {'requested': 0, 'growth_records': 0, 'failures': [], 'all_records_pending': True}
    with connect(get_settings().database_url) as db:
        db.execute("SET statement_timeout='45s'")
        acquired = db.execute('SELECT pg_try_advisory_lock(%s) AS acquired', (LOCK,)).fetchone()['acquired']
        if not acquired:
            return {**result, 'status': 'already_running'}
        try:
            reports = select_reports(db, limit)
            db.commit()
            result['requested'] = len(reports)
            for report in reports:
                details = {'symbol': report['symbol'], 'period': report['report_period'],
                           'official_sha256': report['sha256']}
                run = begin_run(db, TASK)
                db.execute('UPDATE task_runs SET details=%s::jsonb WHERE run_id=%s',
                           (json.dumps(details), run))
                db.commit()
                try:
                    with Path(report['local_path']).open('rb') as handle:
                        if hashlib.file_digest(handle, 'sha256').hexdigest() != report['sha256']:
                            raise ValueError('Official annual PDF hash mismatch')
                    pairs = collect_inputs(report['symbol'], report['report_period'], report['fields'])
                    count = 0
                    for field in sorted(pairs):
                        current, previous = pairs[field]
                        current_id = store_record(db, current, 'pending')
                        previous_id = store_record(db, previous, 'pending')
                        growth = build_growth_evidence(current, previous, str(current_id), str(previous_id))
                        store_record(db, growth, 'pending')
                        count += 1
                    end_run(db, run, 'succeeded', {**details, 'growth_records': count})
                    db.commit()
                    result['growth_records'] += count
                except Exception as error:
                    record_failed_run(db, run, TASK, {**details, 'error': str(error)[:1000]})
                    db.commit()
                    result['failures'].append({**details, 'error': str(error)[:1000]})
        finally:
            db.rollback()
            db.execute('SELECT pg_advisory_unlock(%s)', (LOCK,))
            db.commit()
    return result
