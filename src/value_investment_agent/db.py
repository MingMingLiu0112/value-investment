from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from .models import SourceRecord
from .filing_extract import ANNUAL_BACKFILL_PARSER_VERSION
from .universe import UNIVERSE
from .financial_institutions import financial_gate_message, provisional_financial_type
from .financial_quality import FinancialQualityResult


@contextmanager
def connect(database_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        yield connection


def initialize(database_url: str, schema_path: Path) -> None:
    with connect(database_url) as connection:
        connection.execute(schema_path.read_text(encoding='utf-8'))
        with connection.cursor() as cursor:
            cursor.executemany(
            """INSERT INTO instruments(symbol, name, sector, strategy_type)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (symbol) DO UPDATE SET name = EXCLUDED.name, sector = EXCLUDED.sector,
                 strategy_type = EXCLUDED.strategy_type""",
            UNIVERSE,
            )
        connection.execute(
            """DO $$ BEGIN
                 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'value_agent_reader') THEN
                   GRANT SELECT ON ALL TABLES IN SCHEMA public TO value_agent_reader;
                   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO value_agent_reader;
                 END IF;
               END $$"""
        )


def upsert_instruments(connection: psycopg.Connection, instruments: list[dict]) -> None:
    rows = [(row['symbol'], row['name'], row.get('sector'), '全市场初筛') for row in instruments]
    if not rows:
        return
    connection.cursor().executemany(
        """INSERT INTO instruments(symbol, name, sector, strategy_type)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (symbol) DO UPDATE SET name = EXCLUDED.name,
             sector = CASE WHEN EXCLUDED.sector = '待行业映射' THEN instruments.sector ELSE EXCLUDED.sector END""",
        rows,
    )


def _store_document(connection: psycopg.Connection, *, source_name: str, source_url: str,
                    published_at, fetched_at, parser_version: str, raw_payload: bytes,
                    metadata: dict | None = None, local_path: str | None = None) -> uuid.UUID:
    document_id = uuid.uuid4()
    source_id = hashlib.sha256(raw_payload).hexdigest()
    cursor = connection.execute(
        """INSERT INTO raw_documents(document_id, source_name, source_url, published_at, fetched_at, parser_version, sha256, local_path, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (sha256) DO UPDATE SET source_name = EXCLUDED.source_name,
             source_url = EXCLUDED.source_url, published_at = EXCLUDED.published_at,
             fetched_at = EXCLUDED.fetched_at, parser_version = EXCLUDED.parser_version,
             metadata = EXCLUDED.metadata,
             local_path = COALESCE(NULLIF(EXCLUDED.local_path, ''), raw_documents.local_path)
           RETURNING document_id""",
        (document_id, source_name, source_url, published_at, fetched_at, parser_version, source_id, local_path,
         json.dumps(metadata or {}, ensure_ascii=False)),
    )
    return cursor.fetchone()['document_id']


def begin_run(connection: psycopg.Connection, task_name: str) -> uuid.UUID:
    run_id = uuid.uuid4()
    connection.execute(
        'INSERT INTO task_runs(run_id, task_name, started_at, status) VALUES (%s, %s, clock_timestamp(), %s)',
        (run_id, task_name, 'running'),
    )
    return run_id


def end_run(connection: psycopg.Connection, run_id: uuid.UUID, status: str, details: dict) -> None:
    connection.execute(
        'UPDATE task_runs SET finished_at = clock_timestamp(), status = %s, details = %s WHERE run_id = %s',
        (status, json.dumps(details, ensure_ascii=False), run_id),
    )


def record_failed_run(connection: psycopg.Connection, run_id: uuid.UUID, task_name: str, details: dict) -> None:
    """Persist a failure after rolling back the work transaction that caused it."""
    connection.rollback()
    previous = connection.execute(
        'SELECT details FROM task_runs WHERE run_id = %s', (run_id,),
    ).fetchone()
    reconstructed = previous is None or (previous.get('details') or {}).get('start_time_reconstructed') is True
    failure_details = {**details, 'start_time_reconstructed': reconstructed,
                       'failure_logged_after_rollback': True}
    connection.execute(
        """INSERT INTO task_runs(run_id, task_name, started_at, finished_at, status, details)
           VALUES (%s, %s, clock_timestamp(), clock_timestamp(), 'failed', %s)
           ON CONFLICT (run_id) DO UPDATE SET finished_at = clock_timestamp(), status = 'failed', details = EXCLUDED.details""",
        (run_id, task_name, json.dumps(failure_details, ensure_ascii=False)),
    )


def store_record(
    connection: psycopg.Connection,
    record: SourceRecord,
    validation_status: str = 'pending',
    human_reviewed: bool = False,
) -> uuid.UUID:
    source_uuid = _store_document(
        connection, source_name=record.source_name, source_url=record.source_url,
        published_at=record.published_at, fetched_at=record.fetched_at, parser_version=record.parser_version,
        raw_payload=record.raw_payload, metadata=record.audit_metadata(), local_path=record.local_path,
    )
    if validation_status == 'pending' and not human_reviewed:
        existing = connection.execute(
            """SELECT data_point_id FROM data_points
                 WHERE symbol=%s AND field_name=%s AND period_label=%s AND value=%s
                   AND unit=%s AND source_id=%s AND validation_status='pending'
                   AND human_reviewed=false AND metadata=%s::jsonb
                 ORDER BY created_at DESC LIMIT 1""",
            (record.symbol,record.field_name,record.period_label,record.value,record.unit,
             source_uuid,json.dumps(record.point_metadata or {},ensure_ascii=False)),
        ).fetchone()
        if existing:
            return existing['data_point_id']
    data_point_id = uuid.uuid4()
    connection.execute(
        """INSERT INTO data_points(data_point_id, symbol, field_name, period_label, value, unit, source_id, validation_status, human_reviewed, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (data_point_id, record.symbol, record.field_name, record.period_label, record.value,
         record.unit, source_uuid, validation_status, human_reviewed,
         json.dumps(record.point_metadata or {}, ensure_ascii=False)),
    )
    return data_point_id


def store_market_screen(
    connection: psycopg.Connection, candidates: list, raw_payload: bytes, fetched_at: datetime,
    source_name: str = 'AkShare / Eastmoney all-A market snapshot',
    source_url: str = 'https://quote.eastmoney.com/center/gridlist.html#hs_a_board',
    parser_version: str = 'market-screen-v1-eastmoney',
    local_path: str | None = None,
) -> int:
    if not candidates:
        return 0
    try:
        snapshot = json.loads(raw_payload.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        snapshot = {}
    source_uuid = _store_document(
        connection, source_name=source_name, source_url=source_url, published_at=None,
        fetched_at=fetched_at, parser_version=parser_version, raw_payload=raw_payload,
        metadata={
            'candidate_count': len(candidates), 'scope': 'all A-share initial screen',
            'snapshot_source': snapshot.get('source'),
            'fallback_reason': snapshot.get('fallback_reason'),
            'industry_mapping_count': snapshot.get('industry_mapping_count'),
            'industry_mapping_source': snapshot.get('industry_mapping_source'),
            'industry_mapping_error': snapshot.get('industry_mapping_error'),
            'valuation_cross_check': snapshot.get('valuation_cross_check'),
            'coverage_audit': snapshot.get('coverage_audit'),
        },
        local_path=local_path,
    )
    screen_date = fetched_at.date()
    # A screen is a coherent as-of snapshot. Replacing its rows atomically
    # prevents an earlier degraded fallback run from leaking into the Excel UI.
    connection.execute('DELETE FROM market_screen_results WHERE screen_date = %s', (screen_date,))
    connection.cursor().executemany(
        """INSERT INTO market_screen_results(symbol, screen_date, sector, board, current_price, pe, pb, market_cap, initial_score, status, source_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (symbol, screen_date) DO UPDATE SET sector = EXCLUDED.sector, board = EXCLUDED.board,
             current_price = EXCLUDED.current_price, pe = EXCLUDED.pe, pb = EXCLUDED.pb,
             market_cap = EXCLUDED.market_cap, initial_score = EXCLUDED.initial_score,
             status = EXCLUDED.status, source_id = EXCLUDED.source_id, created_at = now()""",
        [(candidate.symbol, screen_date, candidate.sector, candidate.board, candidate.current_price, candidate.pe, candidate.pb,
          candidate.market_cap, candidate.score, candidate.status, source_uuid) for candidate in candidates],
    )
    cross_check = snapshot.get('valuation_cross_check') or {}
    matched = {
        str(row.get('代码',row.get('symbol',row.get('code','')))).zfill(6): row['price_cross_check']
        for row in snapshot.get('rows',[])
        if (row.get('price_cross_check') or {}).get('status') == 'matched'
    }
    if cross_check.get('sina_status') == 'accepted':
        # The all-market snapshot already retained both price sources, tolerance
        # and conflicts in its immutable source document. Reuse that document
        # rather than creating an unauditable per-symbol price fetch.
        connection.cursor().executemany(
            """INSERT INTO data_points(data_point_id, symbol, field_name, period_label, value, unit, source_id, validation_status, human_reviewed, metadata)
               VALUES (%s, %s, 'current_price', %s, %s, 'CNY/share', %s, 'verified', false, %s)""",
            [
                (uuid.uuid4(), candidate.symbol, fetched_at.strftime('%Y-%m-%d %H:%M'), candidate.current_price, source_uuid,
                 json.dumps({
                     'automatic_cross_source_verification': True,
                     'verification_method': 'tencent_all_market_price_plus_sina_snapshot',
                     'price_tolerance': cross_check.get('price_tolerance'),
                     'market_snapshot_source_id': str(source_uuid),
                     'per_symbol_price_evidence': matched[candidate.symbol],
                 }, ensure_ascii=False))
                for candidate in candidates if candidate.symbol in matched
            ],
        )
    return len(candidates)


def current_market_candidate_symbols(connection: psycopg.Connection) -> list[str]:
    """Return the latest all-market screen population for local-only valuation."""
    return [
        row['symbol'] for row in connection.execute(
            """SELECT symbol FROM market_screen_results
                 WHERE screen_date = (SELECT max(screen_date) FROM market_screen_results)
                 ORDER BY symbol"""
        ).fetchall()
    ]


def enqueue_financial_enrichment(connection: psycopg.Connection, candidates: list, screen_date) -> int:
    """Queue public-screened companies for bounded official-filing collection."""
    if not candidates:
        return 0
    cursor = connection.cursor()
    cursor.executemany(
        """INSERT INTO financial_enrichment_queue(symbol, screen_date, priority_score, status)
           VALUES (%s, %s, %s, 'pending_official_filings')
           ON CONFLICT (symbol) DO UPDATE SET screen_date = EXCLUDED.screen_date,
             priority_score = EXCLUDED.priority_score,
             status = CASE
               WHEN financial_enrichment_queue.status IN ('official_filings_archived', 'processing')
                 THEN financial_enrichment_queue.status
               ELSE 'pending_official_filings'
             END,
             updated_at = now()""",
        [(candidate.symbol, screen_date, candidate.score) for candidate in candidates],
    )
    return cursor.rowcount


def claim_financial_enrichment_batch(connection: psycopg.Connection, limit: int) -> list[dict]:
    """Claim a small batch without keeping a database transaction open during downloads."""
    rows = connection.execute(
        """WITH next_batch AS (
             SELECT q.symbol
             FROM financial_enrichment_queue q
             WHERE q.status IN ('pending_official_filings', 'retry')
                OR (q.status = 'processing' AND q.updated_at < now() - interval '3 hours')
                OR (q.status = 'official_filings_archived'
                    AND q.updated_at < now() - interval '1 day'
                    AND EXISTS (
                        SELECT 1 FROM market_screen_results m
                        WHERE m.symbol = q.symbol
                          AND m.screen_date = (SELECT max(screen_date) FROM market_screen_results)
                    ))
             ORDER BY q.updated_at, q.priority_score DESC, q.symbol
             FOR UPDATE SKIP LOCKED
             LIMIT %s
           )
           UPDATE financial_enrichment_queue q
           SET status = 'processing', attempts = q.attempts + 1, updated_at = now(), last_error = NULL
           FROM next_batch b
           WHERE q.symbol = b.symbol
           RETURNING q.symbol, q.priority_score,
             (SELECT i.name FROM instruments i WHERE i.symbol = q.symbol) AS name""",
        (limit,),
    ).fetchall()
    connection.commit()
    return rows


def finish_financial_enrichment(connection: psycopg.Connection, symbol: str, error: str | None = None) -> None:
    # Failed statutory-source retrieval is a transport/data-source condition,
    # not a reason to require a human to keep the queue moving. The next bounded
    # run retries it and the adapter can select its configured fallback source.
    status = 'official_filings_archived' if error is None else 'retry'
    connection.execute(
        """UPDATE financial_enrichment_queue
           SET status = %s,
               last_error = %s, updated_at = now()
           WHERE symbol = %s""",
        (status, error[:1000] if error else None, symbol),
    )
    connection.commit()


def sector_map(connection: psycopg.Connection) -> dict[str, str]:
    return {
        row['symbol']: row['sector']
        for row in connection.execute(
            """SELECT symbol, sector FROM instruments
                 WHERE sector IS NOT NULL AND sector <> '待行业映射'
                   AND sector NOT IN ('主板', '创业板', '科创板', '北交所', '待板块映射')"""
        ).fetchall()
    }


def store_official_disclosure(connection: psycopg.Connection, disclosure: dict) -> None:
    """Register a downloaded exchange filing without treating it as parsed data."""
    connection.execute(
        """INSERT INTO official_disclosures(
             disclosure_id, symbol, report_period, report_kind, title, source_name,
             source_url, published_at, sha256, local_path, fetched_at, review_status, report_assurance
           ) VALUES (%(disclosure_id)s, %(symbol)s, %(report_period)s, %(report_kind)s,
             %(title)s, %(source_name)s, %(source_url)s, %(published_at)s, %(sha256)s,
             %(local_path)s, %(fetched_at)s, 'pending', %(report_assurance)s)
           ON CONFLICT (symbol, sha256) DO UPDATE SET fetched_at = EXCLUDED.fetched_at,
             local_path = EXCLUDED.local_path, source_url = EXCLUDED.source_url,
             report_assurance = EXCLUDED.report_assurance,
             archive_status = 'server_resident', archive_uri = NULL,
             archived_at = NULL, archive_manifest_sha256 = NULL""",
        disclosure,
    )


def claim_disclosures_for_extraction(connection: psycopg.Connection, limit: int) -> list[dict]:
    rows = connection.execute(
        """WITH next_batch AS (
             SELECT disclosure_id FROM official_disclosures
             WHERE archive_status = 'server_resident'
               AND review_status <> 'rejected' AND (extraction_status = 'pending'
                OR (extraction_status IN ('extracted', 'no_candidates')
                    AND extraction_parser_version IS DISTINCT FROM %s)
                OR (extraction_status = 'processing' AND extraction_claimed_at < now() - interval '3 hours')
                OR (extraction_status = 'failed' AND extraction_attempts < 5))
             ORDER BY CASE WHEN EXISTS (
                          SELECT 1 FROM market_screen_results m
                          WHERE m.symbol=official_disclosures.symbol
                            AND m.screen_date=(SELECT max(screen_date) FROM market_screen_results)
                        ) THEN CASE WHEN report_kind='annual' THEN 0 ELSE 1 END ELSE 2 END,
                      report_period DESC,
                      CASE extraction_status WHEN 'failed' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
                      published_at DESC
             FOR UPDATE SKIP LOCKED LIMIT %s
           )
           UPDATE official_disclosures o
           SET extraction_status = 'processing', extraction_claimed_at = now(),
               extraction_attempts = o.extraction_attempts + 1
           FROM next_batch b WHERE o.disclosure_id = b.disclosure_id
           RETURNING o.disclosure_id, o.symbol, o.report_period, o.sha256, o.local_path""",
        (ANNUAL_BACKFILL_PARSER_VERSION, limit),
    ).fetchall()
    connection.commit()
    return rows


def mark_disclosures_cold_archived(connection: psycopg.Connection, *, manifest_sha256: str,
                                  archive_uri: str, disclosure_ids: list[str]) -> int:
    """Record verified cold-copy receipt without deleting server-side evidence."""
    if not disclosure_ids:
        return 0
    if len(manifest_sha256) != 64 or any(char not in '0123456789abcdef' for char in manifest_sha256.lower()):
        raise ValueError('manifest_sha256 must be a SHA-256 hex digest')
    if not archive_uri.strip():
        raise ValueError('archive_uri is required')
    rows = connection.execute(
        """UPDATE official_disclosures
              SET archive_status = 'cold_archived', archive_uri = %s,
                  archived_at = now(), archive_manifest_sha256 = %s
            WHERE disclosure_id = ANY(%s::uuid[])
              AND archive_status = 'server_resident'
              AND extraction_status IN ('extracted', 'no_candidates')
          RETURNING disclosure_id""",
        (archive_uri, manifest_sha256.lower(), disclosure_ids),
    ).fetchall()
    if len(rows) != len(disclosure_ids):
        raise ValueError('Cold archive state update refused: manifest includes non-resident or unfinished disclosures')
    connection.commit()
    return len(rows)


def candidate_evidence_excerpt(row: dict) -> str:
    excerpt = row['excerpt']
    page = row.get('unit_evidence_page')
    declaration = row.get('unit_evidence_excerpt')
    if page is not None or declaration is not None:
        if type(page) is not int or page < 1 or not isinstance(declaration, str) or not declaration.strip():
            raise ValueError('Incomplete report-unit evidence')
        prefix = f'单位依据（PDF第{page}页）：{declaration}\n数值原文：\n'
        if len(prefix) > 500:
            raise ValueError('Unit evidence exceeds excerpt budget')
        excerpt = prefix + excerpt
    return excerpt[:1000]


def store_filing_candidates(connection: psycopg.Connection, disclosure_id: uuid.UUID, candidates: list[dict]) -> int:
    if not candidates:
        return 0
    connection.cursor().executemany(
        """INSERT INTO filing_candidates(candidate_id, disclosure_id, field_name, value, unit,
              page_number, source_label, excerpt, parser_version, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (disclosure_id, field_name, page_number, source_label) DO NOTHING""",
        [(uuid.uuid4(), disclosure_id, row['field_name'], row['value'], row['unit'], row['page'],
          row['source_label'], candidate_evidence_excerpt(row), ANNUAL_BACKFILL_PARSER_VERSION, row['status']) for row in candidates],
    )
    return len(candidates)


def finish_disclosure_extraction(connection: psycopg.Connection, disclosure_id: uuid.UUID, candidates: int = 0,
                                 error: str | None = None) -> None:
    status = 'failed' if error else ('extracted' if candidates else 'no_candidates')
    connection.execute(
        'UPDATE official_disclosures SET extraction_status = %s, extraction_claimed_at = NULL, extraction_error = %s, extraction_parser_version = %s WHERE disclosure_id = %s',
        (status, error[:1000] if error else None, ANNUAL_BACKFILL_PARSER_VERSION, disclosure_id),
    )
    connection.commit()


def latest_points(connection: psycopg.Connection, *, annual_only: bool = False,
                  symbols: list[str] | None = None) -> list[dict]:
    rows = connection.execute(
        """WITH ranked AS (SELECT
              p.data_point_id, p.symbol, p.field_name, p.period_label, p.value, p.unit, p.validation_status,
              p.human_reviewed, p.metadata, p.created_at, d.document_id AS source_id, d.source_name, d.source_url,
              d.published_at, d.fetched_at, d.parser_version, d.sha256,
              DENSE_RANK() OVER (PARTITION BY p.symbol, p.field_name
                ORDER BY p.period_label DESC, p.created_at DESC) AS latest_rank
            FROM data_points p JOIN raw_documents d ON d.document_id = p.source_id
            WHERE NOT (p.metadata ? 'superseded_by_parser')
              AND (NOT %s OR p.period_label ~ '^[0-9]{4}-12-31$')
              AND (%s::text[] IS NULL OR p.symbol = ANY(%s::text[]))
            ) SELECT * FROM ranked WHERE latest_rank = 1
            ORDER BY symbol, field_name, data_point_id""",
        (annual_only, symbols, symbols),
    ).fetchall()
    return resolve_latest_ties(rows)


def resolve_latest_ties(rows: list[dict]) -> list[dict]:
    """Retain tied evidence and quarantine ambiguity without mutating stored facts."""
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        grouped.setdefault((row['symbol'], row['field_name']), []).append(row)
    result = []
    blocked = set()
    for key, alternatives in grouped.items():
        alternatives = sorted(alternatives, key=lambda p: str(p['data_point_id']))
        chosen = dict(alternatives[0])
        chosen.pop('latest_rank', None)
        chosen['metadata'] = dict(chosen.get('metadata') or {})
        if len(alternatives) > 1:
            chosen['metadata']['latest_tied_point_ids'] = [str(p['data_point_id']) for p in alternatives]
            money_units = {'CNY': Decimal('1'), 'CNY 10K': Decimal('10000'),
                           'CNY 100M': Decimal('100000000')}
            signatures = {(Decimal(str(p['value'])) * money_units.get(p['unit'], Decimal('1')),
                           'CNY' if p['unit'] in money_units else p['unit'], p['validation_status'],
                           bool((p.get('metadata') or {}).get('evidence_quarantine')),
                           (p.get('metadata') or {}).get('automatic_cross_source_verification'))
                          for p in alternatives}
            if len(signatures) > 1:
                chosen['validation_status'] = 'conflict'
                chosen['metadata']['evidence_quarantine'] = 'ambiguous_latest_financial_inputs'
                blocked.add(key)
        result.append(chosen)
    # Cached derivatives must not remain accepted when an upstream input is ambiguous.
    changed = True
    while changed:
        changed = False
        for point in result:
            key = (point['symbol'], point['field_name'])
            inputs = point['metadata'].get('input_facts') or {}
            dependencies = [name for name in inputs if (point['symbol'], name) in blocked]
            if dependencies and key not in blocked:
                point['validation_status'] = 'conflict'
                point['metadata']['evidence_quarantine'] = 'ambiguous_derivation_inputs'
                point['metadata']['ambiguous_input_fields'] = sorted(dependencies)
                blocked.add(key)
                changed = True
    return result


def upsert_valuation(connection: psycopg.Connection, result: dict) -> None:
    connection.execute(
        """INSERT INTO valuation_results(symbol, current_price, fair_value, safety_margin, valuation_status, build_signal, target_weight, data_status, calculation_details)
           VALUES (%(symbol)s, %(current_price)s, %(fair_value)s, %(safety_margin)s, %(valuation_status)s,
             %(build_signal)s, %(target_weight)s, %(data_status)s, %(calculation_details)s)
           ON CONFLICT (symbol) DO UPDATE SET current_price = EXCLUDED.current_price, fair_value = EXCLUDED.fair_value,
             safety_margin = EXCLUDED.safety_margin, valuation_status = EXCLUDED.valuation_status,
             build_signal = EXCLUDED.build_signal, target_weight = EXCLUDED.target_weight,
             data_status = EXCLUDED.data_status, calculation_details = EXCLUDED.calculation_details, calculated_at = now()""",
        {**result, 'calculation_details': json.dumps(result['calculation_details'], ensure_ascii=False)},
    )


def upsert_financial_quality(connection: psycopg.Connection, result: FinancialQualityResult) -> None:
    row = result.database_row()
    connection.execute(
        """INSERT INTO financial_quality_results(
               symbol, model_type, quality_status, total_score, coverage_ratio,
               profitability_score, cash_flow_score, balance_sheet_score, growth_score,
               reasons, calculation_details
             ) VALUES (
               %(symbol)s, %(model_type)s, %(quality_status)s, %(total_score)s, %(coverage_ratio)s,
               %(profitability_score)s, %(cash_flow_score)s, %(balance_sheet_score)s, %(growth_score)s,
               %(reasons)s, %(calculation_details)s
             ) ON CONFLICT (symbol) DO UPDATE SET
               model_type = EXCLUDED.model_type, quality_status = EXCLUDED.quality_status,
               total_score = EXCLUDED.total_score, coverage_ratio = EXCLUDED.coverage_ratio,
               profitability_score = EXCLUDED.profitability_score, cash_flow_score = EXCLUDED.cash_flow_score,
               balance_sheet_score = EXCLUDED.balance_sheet_score, growth_score = EXCLUDED.growth_score,
               reasons = EXCLUDED.reasons, calculation_details = EXCLUDED.calculation_details,
               calculated_at = now()""",
        {**row, "reasons": json.dumps(row["reasons"], ensure_ascii=False),
         "calculation_details": json.dumps(row["calculation_details"], ensure_ascii=False)},
    )


def record_monthly_snapshot(connection: psycopg.Connection, snapshot_month: str) -> int:
    """Freeze the last collected price of a completed month and contemporaneous research state."""
    try:
        datetime.strptime(snapshot_month, '%Y-%m')
    except ValueError as error:
        raise ValueError('snapshot_month must use YYYY-MM') from error
    prices = connection.execute(
        """SELECT DISTINCT ON (p.symbol) p.symbol, p.value
           FROM data_points p
           WHERE p.field_name = 'current_price' AND p.period_label LIKE %s
           ORDER BY p.symbol, p.period_label DESC, p.created_at DESC""",
        (f'{snapshot_month}%',),
    ).fetchall()
    latest_by_symbol: dict[str, dict[str, dict]] = {}
    for point in latest_points(connection):
        latest_by_symbol.setdefault(point['symbol'], {})[point['field_name']] = point
    valuations = {
        row['symbol']: row
        for row in connection.execute('SELECT * FROM valuation_results').fetchall()
    }
    stored = 0
    for price in prices:
        symbol = price['symbol']
        valuation = valuations.get(symbol)
        if valuation is None:
            continue
        fields = latest_by_symbol.get(symbol, {})
        cursor = connection.execute(
            """INSERT INTO monthly_snapshots(
                 symbol, snapshot_month, current_price, fair_value, safety_margin, valuation_status,
                 build_signal, target_weight, revenue_yoy, net_income_yoy, roe, data_status
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (symbol, snapshot_month) DO NOTHING""",
            (
                symbol, snapshot_month, price['value'], valuation['fair_value'], valuation['safety_margin'],
                valuation['valuation_status'], valuation['build_signal'], valuation['target_weight'],
                fields.get('revenue_yoy', {}).get('value'), fields.get('net_income_yoy', {}).get('value'),
                fields.get('roe', {}).get('value'), valuation['data_status'],
            ),
        )
        stored += cursor.rowcount
    return stored


def export_payload(connection: psycopg.Connection) -> dict:
    from .candidate_tracking import export_tracking_observations
    tracking_payload = export_tracking_observations(connection)
    market_audit = connection.execute("""SELECT document_id AS source_id, source_name, source_url,
        fetched_at, sha256, local_path, metadata->'coverage_audit' AS coverage
        FROM raw_documents WHERE metadata->>'scope'='all A-share initial screen'
        ORDER BY fetched_at DESC LIMIT 1""").fetchone()
    from .official_universe import reconcile_security_lists
    official = connection.execute("""SELECT document_id AS source_id, sha256, local_path,
        metadata->'universe' AS universe FROM raw_documents
        WHERE metadata->>'scope'='official_security_universe' ORDER BY fetched_at DESC LIMIT 1""").fetchone()
    official_coverage = reconcile_security_lists(official['universe'] if official else None,market_audit)
    if official:
        official_coverage.update(source_id=str(official['source_id']),sha256=official['sha256'],local_path=official['local_path'])
    if market_audit and market_audit.get('coverage'):
        market_audit['coverage']['official_universe_reconciled'] = official_coverage['reconciled']
    valuations = connection.execute('SELECT * FROM valuation_results ORDER BY symbol').fetchall()
    financial_quality = connection.execute('SELECT * FROM financial_quality_results ORDER BY symbol').fetchall()
    # Cash-flow definitions for banks include changes in deposits and lending;
    # they are not comparable to an industrial company's free cash flow.
    points = [
        point for point in latest_points(connection)
        if not (point['symbol'] in {'600036', '601288'} and point['field_name'] == 'free_cash_flow')
    ]
    audits = connection.execute(
        """SELECT p.symbol, p.field_name, p.period_label, p.value, p.unit, d.source_name, d.source_url,
           d.document_id AS source_id, d.fetched_at, d.published_at, d.parser_version, d.sha256,
           p.validation_status, p.human_reviewed
           FROM data_points p JOIN raw_documents d ON d.document_id = p.source_id
           ORDER BY p.created_at DESC LIMIT 500"""
    ).fetchall()
    monthly_snapshots = connection.execute(
        """SELECT m.*, i.name
           FROM monthly_snapshots m JOIN instruments i ON i.symbol = m.symbol
           ORDER BY m.snapshot_month, m.symbol"""
    ).fetchall()
    disclosures = connection.execute(
        """SELECT DISTINCT ON (o.symbol) o.symbol, o.report_period, o.report_kind,
                  o.title, o.source_name, o.source_url, o.published_at, o.sha256,
                  o.review_status, o.fetched_at
             FROM official_disclosures o
             ORDER BY o.symbol, o.published_at DESC"""
    ).fetchall()
    filing_candidates = connection.execute(
        """SELECT c.candidate_id, c.field_name, c.value, c.unit, c.page_number, c.source_label, c.excerpt,
                  c.status, c.parser_version, o.symbol, i.name, o.report_period, o.report_kind,
                  o.source_url, o.sha256, o.extraction_status
             FROM filing_candidates c JOIN official_disclosures o ON o.disclosure_id = c.disclosure_id
             JOIN instruments i ON i.symbol = o.symbol
             ORDER BY c.created_at DESC LIMIT 2000"""
    ).fetchall()
    filing_verification_summary = {
        row['status']: row['count']
        for row in connection.execute(
            "SELECT status, count(*) AS count FROM filing_candidates GROUP BY status"
        ).fetchall()
    }
    market_candidates = connection.execute(
        """SELECT s.symbol, i.name, s.sector, s.board, s.current_price, s.pe, s.pb, s.market_cap,
                  s.initial_score, s.status, s.screen_date, s.source_id,
                  COALESCE(q.status, 'pending_official_filings') AS enrichment_status,
                  d.source_name AS market_source, d.metadata->>'fallback_reason' AS market_fallback_reason,
                  d.metadata->>'industry_mapping_count' AS industry_mapping_count
             FROM market_screen_results s JOIN instruments i ON i.symbol = s.symbol
             JOIN raw_documents d ON d.document_id = s.source_id
             LEFT JOIN financial_enrichment_queue q ON q.symbol = s.symbol
             WHERE s.screen_date = (SELECT max(screen_date) FROM market_screen_results)
             ORDER BY s.initial_score DESC, s.symbol"""
    ).fetchall()
    reminder_actions = {
        'pending_official_filings': ('补全官方财报，等待Agent自动验证', '全A股初筛通过；Agent将归档官方财报并执行交叉验证。'),
        'processing': ('等待归档完成', '正在从法定披露源归档财报原件；暂不生成交易建议'),
        'official_filings_archived': ('等待Agent自动交叉验证', '官方财报原件已归档；Agent正在校验报告期、单位、页码和独立来源。'),
        'retry': ('重试官方归档', '官方披露归档异常；暂不生成交易建议'),
        'manual_review_required': ('人工核查公告来源', '官方披露归档连续失败；暂不生成交易建议'),
    }
    # Legacy failures are retried automatically; never create a human-review task.
    reminder_actions['manual_review_required'] = (
        'Agent automatic source retry',
        'Official disclosure archiving failed repeatedly; the Agent will retry an alternate statutory source and retain the failure audit. No trade recommendation is generated.',
    )
    valuation_by_symbol = {row['symbol']: row for row in valuations}
    reminders = []
    for row in market_candidates:
        priority = '重点观察' if Decimal(str(row['initial_score'])) >= Decimal('55') else '常规跟踪'
        institution_type = provisional_financial_type(row['name'], row['sector'])
        valuation = valuation_by_symbol.get(row['symbol'])
        if valuation and valuation['build_signal'] == '建仓候选':
            action = '研究建仓候选（不执行交易）'
            reason = '当前价格、合理价值和安全边际均已完成自动交叉验证；系统仅给出研究优先级，不连接券商或自动下单。'
        elif valuation and valuation['build_signal'] == '观察':
            action = '估值观察'
            reason = '估值处于观察区间；继续跟踪安全边际、最新财报和公告变化。'
        elif valuation and valuation['build_signal'] == '等待价格':
            action = '估值偏高，暂不新增仓位'
            reason = '自动验证估值显示安全边际不足；仅提示停止新增仓位，持仓处置仍需结合投资期限和成本。'
        elif institution_type:
            action, reason = financial_gate_message(institution_type)
            if row['pb'] is None:
                reason += ' 当前公共行情快照缺少 PB，须在专用模型复核中补齐。'
        elif row['pb'] is None:
            action = '补全 PB、财报，等待Agent自动验证'
            reason = '当前全市场行情快照缺少 PB；只能作为待补全研究队列，不得按完整估值条件生成交易建议。'
        else:
            action, reason = reminder_actions.get(
                row['enrichment_status'], reminder_actions['pending_official_filings'],
            )
        reminders.append({
            'priority': priority, 'action': action, 'symbol': row['symbol'],
            'name': row['name'], 'sector': row['sector'], 'board': row['board'], 'reason': reason,
            'current_price': row['current_price'], 'pe': row['pe'], 'pb': row['pb'],
            'source_id': row['source_id'], 'as_of': row['screen_date'],
            'enrichment_status': row['enrichment_status'],
            'research_model': f'provisional_{institution_type}' if institution_type else 'general_pending_review',
            'market_source': row['market_source'], 'market_fallback_reason': row['market_fallback_reason'],
            'industry_mapping_count': row['industry_mapping_count'],
            'valuation_signal': valuation['build_signal'] if valuation else '待数据',
            'valuation_status': valuation['valuation_status'] if valuation else '待估值',
            'safety_margin': valuation['safety_margin'] if valuation else None,
            'valuation_data_status': valuation['data_status'] if valuation else '待数据',
        })
    return {
        'valuations': valuations, 'financial_quality': financial_quality, 'points': points, 'audits': audits,
        'annual_points': latest_points(connection, annual_only=True),
        'market_candidate_count': len(market_candidates),
        'market_audit': market_audit,
        'official_coverage': official_coverage,
        'monthly_snapshots': monthly_snapshots, 'disclosures': disclosures,
        'filing_candidates': filing_candidates, 'market_candidates': market_candidates, 'reminders': reminders,
        'filing_verification_summary': filing_verification_summary,
        **tracking_payload,
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
