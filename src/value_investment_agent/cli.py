from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from .adapters import AkshareFinancialAbstractAdapter, AksharePriceAdapter, SinaFinancialAdapter, SinaFinancialStatementsAdapter
from .backup import create_backup, verify_restore
from .db import begin_run, connect, end_run, export_payload, initialize, latest_points, record_monthly_snapshot, store_official_disclosure, store_record, upsert_valuation
from .disclosures import collect_latest_reports
from .dividends import CninfoDividendAdapter, build_payout_ratio_records
from .evidence import load_evidence_manifest
from .filing_extract import extract_candidates
from .quality import as_valuation_row, evaluate
from .settings import get_settings
from .universe import UNIVERSE
from .workbook import sync_workbook
from .valuation import build_reference_records


def _schema_path() -> Path:
    return Path.cwd() / 'sql' / '001_init.sql'


def run_update(prices: bool, financials: bool, sync_excel: bool) -> None:
    settings = get_settings()
    with connect(settings.database_url) as connection:
        run_id = begin_run(connection, 'update')
        try:
            stored = 0
            if prices:
                for record in AksharePriceAdapter().fetch([item[0] for item in UNIVERSE]):
                    store_record(connection, record, 'pending')
                    stored += 1
            if financials:
                for record in SinaFinancialAdapter().fetch([item[0] for item in UNIVERSE]):
                    # Public structured indicators remain review-required until matched to an official filing.
                    store_record(connection, record, 'pending')
                    stored += 1
                for record in AkshareFinancialAbstractAdapter().fetch([item[0] for item in UNIVERSE]):
                    store_record(connection, record, 'pending')
                    stored += 1
                for record in SinaFinancialStatementsAdapter().fetch([item[0] for item in UNIVERSE]):
                    store_record(connection, record, 'pending')
                    stored += 1
                for record in CninfoDividendAdapter().fetch([item[0] for item in UNIVERSE]):
                    store_record(connection, record, 'pending')
                    stored += 1
                for record in build_payout_ratio_records(latest_points(connection), [item[0] for item in UNIVERSE]):
                    store_record(connection, record, 'pending')
                    stored += 1
            for record in build_reference_records(latest_points(connection), [item[0] for item in UNIVERSE]):
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


def import_evidence(manifest: Path) -> None:
    records, validation_status, human_reviewed = load_evidence_manifest(manifest)
    settings = get_settings()
    with connect(settings.database_url) as connection:
        run_id = begin_run(connection, 'import-evidence')
        try:
            for record in records:
                store_record(connection, record, validation_status, human_reviewed)
            end_run(connection, run_id, 'succeeded', {'manifest': str(manifest), 'records_stored': len(records)})
        except Exception as error:
            end_run(connection, run_id, 'failed', {'manifest': str(manifest), 'error': str(error)})
            raise
    print(json.dumps({'status': 'succeeded', 'records_stored': len(records)}, ensure_ascii=False))


def snapshot_month(month: str) -> None:
    settings = get_settings()
    with connect(settings.database_url) as connection:
        run_id = begin_run(connection, 'snapshot-month')
        try:
            stored = record_monthly_snapshot(connection, month)
            end_run(connection, run_id, 'succeeded', {'snapshot_month': month, 'records_stored': stored})
        except Exception as error:
            connection.rollback()
            end_run(connection, run_id, 'failed', {'snapshot_month': month, 'error': str(error)})
            raise
    print(json.dumps({'status': 'succeeded', 'snapshot_month': month, 'records_stored': stored}, ensure_ascii=False))


def collect_filings() -> None:
    """Archive official report originals. Parsing/verification is a separate step."""
    settings = get_settings()
    with connect(settings.database_url) as connection:
        run_id = begin_run(connection, 'collect-filings')
        try:
            records = collect_latest_reports([item[0] for item in UNIVERSE], settings.evidence_directory)
            for record in records:
                store_official_disclosure(connection, record)
            end_run(connection, run_id, 'succeeded', {'filings_stored': len(records)})
        except Exception as error:
            end_run(connection, run_id, 'failed', {'error': str(error)})
            raise
    print(json.dumps({'status': 'succeeded', 'filings_stored': len(records)}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description='价值投资 Agent：研究辅助，不执行交易。')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init-db')
    update = sub.add_parser('update')
    update.add_argument('--prices', action='store_true', help='从 AkShare 拉取公共行情')
    update.add_argument('--financials', action='store_true', help='从 AkShare/Sina 拉取待核验财务指标')
    update.add_argument('--no-sync-excel', action='store_true')
    sub.add_parser('quality')
    sub.add_parser('export-payload')
    sub.add_parser('sync-excel')
    snapshot = sub.add_parser('snapshot-month')
    snapshot.add_argument('--month', required=True, help='Completed calendar month in YYYY-MM form')
    evidence = sub.add_parser('import-evidence')
    evidence.add_argument('--manifest', required=True, type=Path)
    sub.add_parser('backup')
    sub.add_parser('collect-filings')
    candidates = sub.add_parser('extract-filing-candidates')
    candidates.add_argument('--pdf', required=True, type=Path)
    restore = sub.add_parser('restore-verify')
    restore.add_argument('--manifest', required=True, type=Path)
    args = parser.parse_args()
    settings = get_settings()
    if args.command == 'init-db':
        initialize(settings.database_url, _schema_path())
        print('数据库和证券池初始化完成。')
    elif args.command == 'update':
        run_update(args.prices, args.financials, not args.no_sync_excel)
    elif args.command == 'quality':
        run_quality()
    elif args.command == 'export-payload':
        with connect(settings.database_url) as connection:
            print(json.dumps(export_payload(connection), ensure_ascii=False, default=str))
    elif args.command == 'sync-excel':
        with connect(settings.database_url) as connection:
            print(sync_workbook(export_payload(connection), settings.workbook_path, settings.output_directory))
    elif args.command == 'import-evidence':
        import_evidence(args.manifest)
    elif args.command == 'snapshot-month':
        snapshot_month(args.month)
    elif args.command == 'backup':
        print(create_backup(settings.database_url, settings.backup_directory, settings.container_runtime, settings.postgres_container_name))
    elif args.command == 'collect-filings':
        collect_filings()
    elif args.command == 'extract-filing-candidates':
        print(json.dumps(extract_candidates(args.pdf), ensure_ascii=False, indent=2))
    else:
        if not settings.restore_database_url:
            raise RuntimeError('请在 .env 配置隔离的 RESTORE_DATABASE_URL 后再做恢复演练。')
        print(json.dumps(verify_restore(settings.database_url, settings.restore_database_url, args.manifest, settings.container_runtime, settings.restore_container_name), ensure_ascii=False))


if __name__ == '__main__':
    main()
