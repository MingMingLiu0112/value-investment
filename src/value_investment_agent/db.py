from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from .models import SourceRecord
from .universe import UNIVERSE


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
                    metadata: dict | None = None) -> uuid.UUID:
    document_id = uuid.uuid4()
    source_id = hashlib.sha256(raw_payload).hexdigest()
    cursor = connection.execute(
        """INSERT INTO raw_documents(document_id, source_name, source_url, published_at, fetched_at, parser_version, sha256, local_path, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s)
           ON CONFLICT (sha256) DO UPDATE SET fetched_at = EXCLUDED.fetched_at
           RETURNING document_id""",
        (document_id, source_name, source_url, published_at, fetched_at, parser_version, source_id,
         json.dumps(metadata or {}, ensure_ascii=False)),
    )
    return cursor.fetchone()['document_id']


def begin_run(connection: psycopg.Connection, task_name: str) -> uuid.UUID:
    run_id = uuid.uuid4()
    connection.execute(
        'INSERT INTO task_runs(run_id, task_name, started_at, status) VALUES (%s, %s, now(), %s)',
        (run_id, task_name, 'running'),
    )
    return run_id


def end_run(connection: psycopg.Connection, run_id: uuid.UUID, status: str, details: dict) -> None:
    connection.execute(
        'UPDATE task_runs SET finished_at = now(), status = %s, details = %s WHERE run_id = %s',
        (status, json.dumps(details, ensure_ascii=False), run_id),
    )


def record_failed_run(connection: psycopg.Connection, run_id: uuid.UUID, task_name: str, details: dict) -> None:
    """Persist a failure after rolling back the work transaction that caused it."""
    connection.rollback()
    connection.execute(
        """INSERT INTO task_runs(run_id, task_name, started_at, finished_at, status, details)
           VALUES (%s, %s, now(), now(), 'failed', %s)
           ON CONFLICT (run_id) DO UPDATE SET finished_at = now(), status = 'failed', details = EXCLUDED.details""",
        (run_id, task_name, json.dumps(details, ensure_ascii=False)),
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
        raw_payload=record.raw_payload, metadata=record.audit_metadata(),
    )
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
) -> int:
    if not candidates:
        return 0
    source_uuid = _store_document(
        connection, source_name=source_name, source_url=source_url, published_at=None,
        fetched_at=fetched_at, parser_version=parser_version, raw_payload=raw_payload,
        metadata={'candidate_count': len(candidates), 'scope': 'all A-share initial screen'},
    )
    screen_date = fetched_at.date()
    connection.cursor().executemany(
        """INSERT INTO market_screen_results(symbol, screen_date, sector, current_price, pe, pb, market_cap, initial_score, status, source_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (symbol, screen_date) DO UPDATE SET sector = EXCLUDED.sector,
             current_price = EXCLUDED.current_price, pe = EXCLUDED.pe, pb = EXCLUDED.pb,
             market_cap = EXCLUDED.market_cap, initial_score = EXCLUDED.initial_score,
             status = EXCLUDED.status, source_id = EXCLUDED.source_id, created_at = now()""",
        [(candidate.symbol, screen_date, candidate.sector, candidate.current_price, candidate.pe, candidate.pb,
          candidate.market_cap, candidate.score, candidate.status, source_uuid) for candidate in candidates],
    )
    return len(candidates)


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
               WHEN financial_enrichment_queue.status IN ('official_filings_archived', 'processing', 'manual_review_required')
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
             ORDER BY q.priority_score DESC, q.updated_at
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
    connection.execute(
        """UPDATE financial_enrichment_queue
           SET status = CASE
                 WHEN %s::text IS NULL THEN 'official_filings_archived'
                 WHEN attempts >= 3 THEN 'manual_review_required'
                 ELSE 'retry'
               END,
               last_error = %s, updated_at = now()
           WHERE symbol = %s""",
        (error, error[:1000] if error else None, symbol),
    )
    connection.commit()


def sector_map(connection: psycopg.Connection) -> dict[str, str]:
    return {
        row['symbol']: row['sector']
        for row in connection.execute(
            "SELECT symbol, sector FROM instruments WHERE sector IS NOT NULL AND sector <> '待行业映射'"
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
             report_assurance = EXCLUDED.report_assurance""",
        disclosure,
    )


def claim_disclosures_for_extraction(connection: psycopg.Connection, limit: int) -> list[dict]:
    rows = connection.execute(
        """WITH next_batch AS (
             SELECT disclosure_id FROM official_disclosures
             WHERE extraction_status = 'pending'
                OR (extraction_status = 'processing' AND fetched_at < now() - interval '3 hours')
             ORDER BY published_at DESC
             FOR UPDATE SKIP LOCKED LIMIT %s
           )
           UPDATE official_disclosures o SET extraction_status = 'processing'
           FROM next_batch b WHERE o.disclosure_id = b.disclosure_id
           RETURNING o.disclosure_id, o.symbol, o.report_period, o.sha256, o.local_path""",
        (limit,),
    ).fetchall()
    connection.commit()
    return rows


def store_filing_candidates(connection: psycopg.Connection, disclosure_id: uuid.UUID, candidates: list[dict]) -> int:
    if not candidates:
        return 0
    connection.cursor().executemany(
        """INSERT INTO filing_candidates(candidate_id, disclosure_id, field_name, value, unit,
              page_number, source_label, excerpt, parser_version, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'filing-extract-v2', %s)
           ON CONFLICT (disclosure_id, field_name, page_number, source_label) DO NOTHING""",
        [(uuid.uuid4(), disclosure_id, row['field_name'], row['value'], row['unit'], row['page'],
          row['source_label'], row['excerpt'][:1000], row['status']) for row in candidates],
    )
    return len(candidates)


def finish_disclosure_extraction(connection: psycopg.Connection, disclosure_id: uuid.UUID, candidates: int = 0,
                                 error: str | None = None) -> None:
    status = 'failed' if error else ('extracted' if candidates else 'no_candidates')
    connection.execute('UPDATE official_disclosures SET extraction_status = %s WHERE disclosure_id = %s',
                       (status, disclosure_id))
    connection.commit()


def latest_points(connection: psycopg.Connection) -> list[dict]:
    return connection.execute(
        """SELECT DISTINCT ON (p.symbol, p.field_name)
              p.symbol, p.field_name, p.period_label, p.value, p.unit, p.validation_status,
              p.human_reviewed, p.created_at, d.document_id AS source_id, d.source_name, d.source_url,
              d.published_at, d.fetched_at, d.parser_version, d.sha256
            FROM data_points p JOIN raw_documents d ON d.document_id = p.source_id
            ORDER BY p.symbol, p.field_name, p.period_label DESC, p.created_at DESC"""
    ).fetchall()


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
    valuations = connection.execute('SELECT * FROM valuation_results ORDER BY symbol').fetchall()
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
        """SELECT c.field_name, c.value, c.unit, c.page_number, c.source_label, c.excerpt,
                  c.status, c.parser_version, o.symbol, i.name, o.report_period, o.report_kind,
                  o.source_url, o.sha256, o.extraction_status
             FROM filing_candidates c JOIN official_disclosures o ON o.disclosure_id = c.disclosure_id
             JOIN instruments i ON i.symbol = o.symbol
             ORDER BY c.created_at DESC LIMIT 2000"""
    ).fetchall()
    market_candidates = connection.execute(
        """SELECT s.symbol, i.name, s.sector, s.current_price, s.pe, s.pb, s.market_cap,
                  s.initial_score, s.status, s.screen_date, s.source_id,
                  COALESCE(q.status, 'pending_official_filings') AS enrichment_status
             FROM market_screen_results s JOIN instruments i ON i.symbol = s.symbol
             LEFT JOIN financial_enrichment_queue q ON q.symbol = s.symbol
             WHERE s.screen_date = (SELECT max(screen_date) FROM market_screen_results)
             ORDER BY s.initial_score DESC, s.symbol LIMIT 2000"""
    ).fetchall()
    reminder_actions = {
        'pending_official_filings': ('补全财报并人工复核', '全A股初筛通过；公共估值数据待财报和公告原件复核'),
        'processing': ('等待归档完成', '正在从法定披露源归档财报原件；暂不生成交易建议'),
        'official_filings_archived': ('解析财报并人工复核', '官方财报原件已归档；指标尚未完成页码级核验'),
        'retry': ('重试官方归档', '官方披露归档异常；暂不生成交易建议'),
        'manual_review_required': ('人工核查公告来源', '官方披露归档连续失败；暂不生成交易建议'),
    }
    reminders = []
    for row in market_candidates:
        action, reason = reminder_actions.get(
            row['enrichment_status'], reminder_actions['pending_official_filings'],
        )
        reminders.append({
            'priority': '重点观察', 'action': action, 'symbol': row['symbol'],
            'name': row['name'], 'sector': row['sector'], 'reason': reason,
            'current_price': row['current_price'], 'pe': row['pe'], 'pb': row['pb'],
            'source_id': row['source_id'], 'as_of': row['screen_date'],
            'enrichment_status': row['enrichment_status'],
        })
    return {
        'valuations': valuations, 'points': points, 'audits': audits,
        'monthly_snapshots': monthly_snapshots, 'disclosures': disclosures,
        'filing_candidates': filing_candidates, 'market_candidates': market_candidates, 'reminders': reminders,
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
