from __future__ import annotations

import argparse
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from .adapters import AkshareFinancialAbstractAdapter, AksharePriceAdapter, SinaFinancialAdapter, SinaFinancialStatementsAdapter
from .backup import create_backup, verify_restore
from .db import begin_run, claim_disclosures_for_extraction, claim_financial_enrichment_batch, connect, end_run, enqueue_financial_enrichment, export_payload, finish_disclosure_extraction, finish_financial_enrichment, initialize, latest_points, record_failed_run, record_monthly_snapshot, sector_map, store_filing_candidates, store_market_screen, store_official_disclosure, store_record, upsert_instruments, upsert_valuation
from .disclosures import collect_latest_reports
from .dividends import CninfoDividendAdapter, build_payout_ratio_records
from .evidence import load_evidence_manifest
from .candidate_review import automatically_verified_candidates, load_review_rows, reviewed_records, write_review_template
from .filing_extract import extract_candidates
from .quality import as_valuation_row, evaluate
from .market import AllAMarketAdapter
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
            record_failed_run(connection, run_id, 'update', {'error': str(error)})
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


def export_review_template(output: Path) -> None:
    settings = get_settings()
    with connect(settings.database_url) as connection:
        count = write_review_template(connection, output)
    print(json.dumps({'status': 'succeeded', 'review_rows': count, 'output': str(output)}, ensure_ascii=False))


def import_candidate_reviews(review_csv: Path) -> None:
    rows = load_review_rows(review_csv)
    settings = get_settings()
    with connect(settings.database_url) as connection:
        run_id = begin_run(connection, 'import-candidate-reviews')
        try:
            records = reviewed_records(connection, rows)
            for record in records:
                store_record(connection, record, 'verified', True)
            end_run(connection, run_id, 'succeeded', {'review_csv': str(review_csv), 'records_stored': len(records)})
        except Exception as error:
            record_failed_run(connection, run_id, 'import-candidate-reviews', {'review_csv': str(review_csv), 'error': str(error)})
            raise
    print(json.dumps({'status': 'succeeded', 'records_stored': len(records)}, ensure_ascii=False))


def auto_verify_filings(limit: int) -> None:
    """Promote only official filing values with an automatic independent match."""
    settings = get_settings()
    with connect(settings.database_url) as connection:
        run_id = begin_run(connection, 'auto-verify-filings')
        try:
            records = automatically_verified_candidates(connection, limit)
            for candidate_id, record in records:
                store_record(connection, record, 'verified', False)
                connection.execute(
                    "UPDATE filing_candidates SET status = 'automatically_verified' WHERE candidate_id = %s",
                    (candidate_id,),
                )
            end_run(connection, run_id, 'succeeded', {'records_stored': len(records), 'limit': limit})
        except Exception as error:
            record_failed_run(connection, run_id, 'auto-verify-filings', {'error': str(error), 'limit': limit})
            raise
    print(json.dumps({'status': 'succeeded', 'records_stored': len(records)}, ensure_ascii=False))


def collect_secondary_financials(limit: int) -> None:
    """Collect an independent structured cross-check for archived filings."""
    settings = get_settings()
    with connect(settings.database_url) as connection:
        run_id = begin_run(connection, 'collect-secondary-financials')
        rows = connection.execute(
            """SELECT DISTINCT ON (o.symbol) o.symbol
                 FROM official_disclosures o
                 JOIN filing_candidates c ON c.disclosure_id = o.disclosure_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM data_points p JOIN raw_documents d ON d.document_id = p.source_id
                     WHERE p.symbol = o.symbol AND p.period_label = o.report_period
                       AND d.source_name = 'AkShare / Sina financial indicators'
                )
                ORDER BY o.symbol, o.published_at DESC
                LIMIT %s""",
            (limit,),
        ).fetchall()
        stored = failed = 0
        failures: list[dict[str, str]] = []
        try:
            adapter = SinaFinancialAdapter()
            for row in rows:
                try:
                    # A nested transaction becomes a savepoint here, so one
                    # issuer cannot discard previously collected evidence.
                    with connection.transaction():
                        records = adapter.fetch([row['symbol']])
                        for record in records:
                            store_record(connection, record, 'pending')
                    stored += len(records)
                except Exception as error:
                    failures.append({'symbol': row['symbol'], 'error': str(error)[:300]})
                    failed += 1
            end_run(connection, run_id, 'succeeded', {
                'requested': len(rows), 'records_stored': stored, 'failed_symbols': failures,
            })
        except Exception as error:
            record_failed_run(connection, run_id, 'collect-secondary-financials', {'error': str(error)})
            raise
    print(json.dumps({'status': 'succeeded', 'requested': len(rows), 'records_stored': stored, 'failed': failed}, ensure_ascii=False))


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


def collect_filings(symbols: list[str] | None = None) -> None:
    """Archive official report originals. Parsing/verification is a separate step."""
    settings = get_settings()
    with connect(settings.database_url) as connection:
        run_id = begin_run(connection, 'collect-filings')
        try:
            requested_symbols = symbols or [item[0] for item in UNIVERSE]
            issuer_names = {
                row['symbol']: row['name']
                for row in connection.execute(
                    'SELECT symbol, name FROM instruments WHERE symbol = ANY(%s)',
                    (requested_symbols,),
                ).fetchall()
            }
            records = []
            failures = []
            for symbol in requested_symbols:
                try:
                    records.extend(collect_latest_reports([symbol], settings.evidence_directory, issuer_names))
                except Exception as error:
                    # A transient single-issuer failure must not prevent the
                    # bounded enrichment stage from processing other companies.
                    failures.append({'symbol': symbol, 'error': str(error)[:500]})
            for record in records:
                store_official_disclosure(connection, record)
            end_run(connection, run_id, 'succeeded', {
                'filings_stored': len(records), 'failed_symbols': failures,
            })
        except Exception as error:
            record_failed_run(connection, run_id, 'collect-filings', {'error': str(error)})
            raise
    print(json.dumps({
        'status': 'succeeded', 'filings_stored': len(records), 'failed_symbols': len(failures),
    }, ensure_ascii=False))


def enrich_financials(limit: int) -> None:
    """Archive a bounded batch of official reports for screened companies."""
    settings = get_settings()
    with connect(settings.database_url) as connection:
        run_id = begin_run(connection, 'enrich-financials')
        batch = claim_financial_enrichment_batch(connection, limit)
        completed = 0
        failed = 0
        try:
            for item in batch:
                try:
                    records = collect_latest_reports(
                        [item['symbol']], settings.evidence_directory,
                        {item['symbol']: item['name']},
                    )
                    if not records:
                        raise RuntimeError('No statutory reports found')
                    for record in records:
                        store_official_disclosure(connection, record)
                    finish_financial_enrichment(connection, item['symbol'])
                    completed += 1
                except Exception as error:
                    connection.rollback()
                    finish_financial_enrichment(connection, item['symbol'], str(error))
                    failed += 1
            end_run(connection, run_id, 'succeeded', {
                'requested': len(batch), 'completed': completed, 'failed': failed,
            })
        except Exception as error:
            end_run(connection, run_id, 'failed', {'error': str(error)})
            raise
    print(json.dumps({'status': 'succeeded', 'requested': len(batch), 'completed': completed, 'failed': failed}, ensure_ascii=False))


def extract_filing_candidates_batch(limit: int) -> None:
    """Persist review-only page-level candidates from archived statutory PDFs."""
    settings = get_settings()
    with connect(settings.database_url) as connection:
        run_id = begin_run(connection, 'extract-filing-candidates')
        batch = claim_disclosures_for_extraction(connection, limit)
        stored = failed = 0
        for disclosure in batch:
            try:
                packet = extract_candidates(Path(disclosure['local_path']))
                if packet['sha256'] != disclosure['sha256']:
                    raise RuntimeError('Archived PDF hash does not match disclosure record')
                count = store_filing_candidates(connection, disclosure['disclosure_id'], packet['candidates'])
                finish_disclosure_extraction(connection, disclosure['disclosure_id'], count)
                stored += count
            except Exception as error:
                connection.rollback()
                finish_disclosure_extraction(connection, disclosure['disclosure_id'], error=str(error))
                failed += 1
        end_run(connection, run_id, 'succeeded', {'requested': len(batch), 'candidates_stored': stored, 'failed': failed})
    print(json.dumps({'status': 'succeeded', 'requested': len(batch), 'candidates_stored': stored, 'failed': failed}, ensure_ascii=False))


def screen_market(include_industry: bool) -> None:
    settings = get_settings()
    with connect(settings.database_url) as connection:
        run_id = begin_run(connection, 'screen-market')
        try:
            universe, _, candidates, raw, fetched_at, source = AllAMarketAdapter().fetch(include_industry=include_industry)
            upsert_instruments(connection, universe)
            if not include_industry:
                known_sectors = sector_map(connection)
                candidates = [replace(candidate, sector=known_sectors.get(candidate.symbol, candidate.sector)) for candidate in candidates]
            stored = store_market_screen(connection, candidates, raw, fetched_at, *source)
            enqueue_financial_enrichment(connection, candidates, fetched_at.date())
            end_run(connection, run_id, 'succeeded', {'universe_count': len(universe), 'candidate_count': stored})
        except Exception as error:
            record_failed_run(connection, run_id, 'screen-market', {'error': str(error)})
            raise
    print(json.dumps({'status': 'succeeded', 'universe_count': len(universe), 'candidate_count': stored}, ensure_ascii=False))


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
    review_template = sub.add_parser('export-review-template')
    review_template.add_argument('--output', required=True, type=Path)
    reviews = sub.add_parser('import-candidate-reviews')
    reviews.add_argument('--csv', required=True, type=Path)
    auto_verify = sub.add_parser('auto-verify-filings')
    auto_verify.add_argument('--limit', type=int, default=100, choices=range(1, 501), metavar='1-500')
    secondary = sub.add_parser('collect-secondary-financials')
    secondary.add_argument('--limit', type=int, default=25, choices=range(1, 101), metavar='1-100')
    sub.add_parser('backup')
    filings = sub.add_parser('collect-filings')
    filings.add_argument('--symbols', help='Comma-separated A-share codes; defaults to the tracked sample universe')
    enrichment = sub.add_parser('enrich-financials')
    enrichment.add_argument('--limit', type=int, default=5, choices=range(1, 21), metavar='1-20')
    extraction = sub.add_parser('extract-filing-candidates-batch')
    extraction.add_argument('--limit', type=int, default=10, choices=range(1, 21), metavar='1-20')
    market = sub.add_parser('screen-market')
    market.add_argument('--without-industry', action='store_true')
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
    elif args.command == 'export-review-template':
        export_review_template(args.output)
    elif args.command == 'import-candidate-reviews':
        import_candidate_reviews(args.csv)
    elif args.command == 'auto-verify-filings':
        auto_verify_filings(args.limit)
    elif args.command == 'collect-secondary-financials':
        collect_secondary_financials(args.limit)
    elif args.command == 'snapshot-month':
        snapshot_month(args.month)
    elif args.command == 'backup':
        print(create_backup(settings.database_url, settings.backup_directory, settings.container_runtime, settings.postgres_container_name))
    elif args.command == 'collect-filings':
        requested_symbols = None
        if args.symbols:
            requested_symbols = [symbol.strip().zfill(6) for symbol in args.symbols.split(',') if symbol.strip()]
            if not requested_symbols or any(not symbol.isdigit() or len(symbol) != 6 for symbol in requested_symbols):
                raise ValueError('--symbols must be comma-separated six-digit A-share codes')
        collect_filings(requested_symbols)
    elif args.command == 'enrich-financials':
        enrich_financials(args.limit)
    elif args.command == 'extract-filing-candidates-batch':
        extract_filing_candidates_batch(args.limit)
    elif args.command == 'screen-market':
        screen_market(not args.without_industry)
    elif args.command == 'extract-filing-candidates':
        print(json.dumps(extract_candidates(args.pdf), ensure_ascii=False, indent=2))
    else:
        if not settings.restore_database_url:
            raise RuntimeError('请在 .env 配置隔离的 RESTORE_DATABASE_URL 后再做恢复演练。')
        print(json.dumps(verify_restore(settings.database_url, settings.restore_database_url, args.manifest, settings.container_runtime, settings.restore_container_name), ensure_ascii=False))


if __name__ == '__main__':
    main()
