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


def store_record(
    connection: psycopg.Connection,
    record: SourceRecord,
    validation_status: str = 'pending',
    human_reviewed: bool = False,
) -> uuid.UUID:
    document_id = uuid.uuid4()
    source_id = hashlib.sha256(record.raw_payload).hexdigest()
    cursor = connection.execute(
        """INSERT INTO raw_documents(document_id, source_name, source_url, published_at, fetched_at, parser_version, sha256, local_path, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (sha256) DO UPDATE SET fetched_at = EXCLUDED.fetched_at,
             local_path = COALESCE(EXCLUDED.local_path, raw_documents.local_path)
           RETURNING document_id""",
        (document_id, record.source_name, record.source_url, record.published_at, record.fetched_at,
         record.parser_version, source_id, record.local_path, json.dumps(record.audit_metadata(), ensure_ascii=False)),
    )
    source_row = cursor.fetchone()
    source_uuid = source_row['document_id']
    data_point_id = uuid.uuid4()
    connection.execute(
        """INSERT INTO data_points(data_point_id, symbol, field_name, period_label, value, unit, source_id, validation_status, human_reviewed, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (data_point_id, record.symbol, record.field_name, record.period_label, record.value,
         record.unit, source_uuid, validation_status, human_reviewed,
         json.dumps(record.point_metadata or {}, ensure_ascii=False)),
    )
    return data_point_id


def store_official_disclosure(connection: psycopg.Connection, disclosure: dict) -> None:
    """Register a downloaded exchange filing without treating it as parsed data."""
    connection.execute(
        """INSERT INTO official_disclosures(
             disclosure_id, symbol, report_period, report_kind, title, source_name,
             source_url, published_at, sha256, local_path, fetched_at, review_status
           ) VALUES (%(disclosure_id)s, %(symbol)s, %(report_period)s, %(report_kind)s,
             %(title)s, %(source_name)s, %(source_url)s, %(published_at)s, %(sha256)s,
             %(local_path)s, %(fetched_at)s, 'pending')
           ON CONFLICT (symbol, sha256) DO UPDATE SET fetched_at = EXCLUDED.fetched_at,
             local_path = EXCLUDED.local_path, source_url = EXCLUDED.source_url""",
        disclosure,
    )


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
    return {
        'valuations': valuations, 'points': points, 'audits': audits,
        'monthly_snapshots': monthly_snapshots, 'disclosures': disclosures,
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
