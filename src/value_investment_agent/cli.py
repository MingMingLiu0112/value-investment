from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from .adapters import AksharePriceAdapter
from .backup import create_backup, verify_restore
from .db import begin_run, connect, end_run, export_payload, initialize, latest_points, store_record, upsert_valuation
from .quality import as_valuation_row, evaluate
from .settings import get_settings
from .universe import UNIVERSE
from .workbook import sync_workbook


def _schema_path() -> Path:
    return Path.cwd() / 'sql' / '001_init.sql'


def run_update(prices: bool, sync_excel: bool) -> None:
    settings = get_settings()
    with connect(settings.database_url) as connection:
        run_id = begin_run(connection, 'update')
        try:
            stored = 0
            if prices:
                for record in AksharePriceAdapter().fetch([item[0] for item in UNIVERSE]):
                    store_record(connection, record, 'pending')
                    stored += 1
            grouped: dict[str, list[dict]] = {item[0]: [] for item in UNIVERSE}
            for point in latest_points(connection):
                grouped[point['symbol']].append(point)
            for symbol, rows in grouped.items():
                result = evaluate(symbol, rows, settings.data_max_age_hours, Decimal(str(settings.price_conflict_tolerance)))
                upsert_valuation(connection, as_valuation_row(result))
            output = None
            if sync_excel:
                output = str(sync_workbook(export_payload(connection), settings.workbook_path, settings.output_directory))
            end_run(connection, run_id, 'succeeded', {'records_stored': stored, 'workbook': output})
            print(json.dumps({'status': 'succeeded', 'records_stored': stored, 'workbook': output}, ensure_ascii=False))
        except Exception as error:
            end_run(connection, run_id, 'failed', {'error': str(error)})
            raise


def run_quality() -> None:
    settings = get_settings()
    with connect(settings.database_url) as connection:
        rows = connection.execute('SELECT symbol, data_status, build_signal, calculated_at FROM valuation_results ORDER BY symbol').fetchall()
    print(json.dumps(rows, ensure_ascii=False, default=str, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description='价值投资 Agent：研究辅助，不执行交易。')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init-db')
    update = sub.add_parser('update')
    update.add_argument('--prices', action='store_true', help='从 AkShare 拉取公共行情')
    update.add_argument('--no-sync-excel', action='store_true')
    sub.add_parser('quality')
    sub.add_parser('export-payload')
    sub.add_parser('sync-excel')
    sub.add_parser('backup')
    restore = sub.add_parser('restore-verify')
    restore.add_argument('--manifest', required=True, type=Path)
    args = parser.parse_args()
    settings = get_settings()
    if args.command == 'init-db':
        initialize(settings.database_url, _schema_path())
        print('数据库和证券池初始化完成。')
    elif args.command == 'update':
        run_update(args.prices, not args.no_sync_excel)
    elif args.command == 'quality':
        run_quality()
    elif args.command == 'export-payload':
        with connect(settings.database_url) as connection:
            print(json.dumps(export_payload(connection), ensure_ascii=False, default=str))
    elif args.command == 'sync-excel':
        with connect(settings.database_url) as connection:
            print(sync_workbook(export_payload(connection), settings.workbook_path, settings.output_directory))
    elif args.command == 'backup':
        print(create_backup(settings.database_url, settings.backup_directory, settings.container_runtime, settings.postgres_container_name))
    else:
        if not settings.restore_database_url:
            raise RuntimeError('请在 .env 配置隔离的 RESTORE_DATABASE_URL 后再做恢复演练。')
        print(json.dumps(verify_restore(settings.database_url, settings.restore_database_url, args.manifest, settings.container_runtime, settings.restore_container_name), ensure_ascii=False))


if __name__ == '__main__':
    main()
