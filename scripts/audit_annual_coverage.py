"""Read-only candidate-pool coverage; parser migration is not financial completeness."""
from collections import Counter
import json
from filing_extract import ANNUAL_BACKFILL_PARSER_VERSION

from value_investment_agent.db import connect, current_market_candidate_symbols
from value_investment_agent.settings import get_settings


with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
    db.execute("SET statement_timeout='45s'")
    symbols = set(current_market_candidate_symbols(db))
    reports = db.execute("""SELECT DISTINCT ON (symbol) symbol,report_period,sha256
        FROM official_disclosures WHERE symbol=ANY(%s) AND report_kind='annual'
        ORDER BY symbol,report_period DESC,published_at DESC""", (list(symbols),)).fetchall()
    migrations = db.execute("""SELECT details->>'symbol' AS symbol,
        details->>'report_period' AS report_period,details->>'official_sha256' AS sha256
        FROM task_runs WHERE task_name='annual-parser-migration' AND status='succeeded'
        AND details->>'parser_version'=%s""",(ANNUAL_BACKFILL_PARSER_VERSION,)).fetchall()
    migrated = {(r['symbol'], r['report_period'], r['sha256']) for r in migrations}
    verified = db.execute("""SELECT DISTINCT symbol,period_label FROM data_points
        WHERE symbol=ANY(%s) AND validation_status='verified'
          AND metadata->>'automatic_cross_source_verification'='true'
          AND NOT (COALESCE(metadata,'{}'::jsonb) ? 'evidence_quarantine')""", (list(symbols),)).fetchall()
    verified_periods = {(r['symbol'], r['period_label']) for r in verified}
    archived = {r['symbol'] for r in reports}
    recent_collection = db.execute("""SELECT started_at,finished_at,status,details
        FROM task_runs WHERE task_name='collect-filings'
        ORDER BY started_at DESC LIMIT 1""").fetchone()
    pending = [r['symbol'] for r in reports
               if (r['symbol'], r['report_period'], r['sha256']) not in migrated]
    result = {
        'candidate_count': len(symbols),
        'parser_version': ANNUAL_BACKFILL_PARSER_VERSION,
        'latest_collection_run': recent_collection,
        'retained_annual_count': len(reports),
        'retained_period_counts': dict(Counter(r['report_period'] for r in reports)),
        'older_than_pool_latest_annual': [
            {'symbol': r['symbol'], 'report_period': r['report_period']} for r in reports
            if r['report_period'] < max(item['report_period'] for item in reports)],
        'no_retained_annual_symbols': sorted(symbols - archived),
        'parser_migrated_count': len(reports) - len(pending),
        'parser_pending_count': len(pending),
        'parser_pending_first_20': sorted(pending)[:20],
        'latest_retained_annual_with_any_verified_fact': sum(
            (r['symbol'], r['report_period']) in verified_periods for r in reports),
        'scope_note': 'Any verified fact or successful parser migration does not prove complete financial inputs.',
    }
    print(json.dumps(result, sort_keys=True, default=str))
