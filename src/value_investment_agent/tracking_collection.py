"""Daily quote collection without mutating the initial screening population."""
import hashlib
import json
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .candidate_tracking import normalize_tracking_quotes, track_candidates, store_tracking_observations
from .db import _store_document, begin_run, connect, end_run, record_failed_run
from .market import AllAMarketAdapter
from .quote_session_collection import collect_session_bundle
from .quote_sessions import evaluate_quote_session


def archive_snapshot(directory, raw, *, subdirectory='tracking_snapshots'):
    if subdirectory not in {'tracking_snapshots', 'financial_snapshots'}:
        raise ValueError('Unsupported evidence namespace')
    directory = Path(directory) / subdirectory
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw).hexdigest()
    destination = directory / (digest + '.json')
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise ValueError('Tracking evidence hash mismatch')
        return destination
    if shutil.disk_usage(directory).free < 2 * 1024**3 + len(raw):
        raise OSError('Low disk: preserve database reserve')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, suffix='.part', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def collect_candidate_quotes(settings, adapter=None):
    with connect(settings.database_url) as connection:
        run_id = begin_run(connection, 'track-candidates')
        connection.commit()
        try:
            members = connection.execute("""SELECT * FROM market_screen_results
                WHERE screen_date = (SELECT max(screen_date) FROM market_screen_results)
                ORDER BY symbol""").fetchall()
            connection.commit()
            if not members:
                raise ValueError('No initial screening population available')
            # No transaction or row lock is held while fetching external sources.
            _, _, _, raw, fetched_at, source = (adapter or AllAMarketAdapter()).fetch(include_industry=False)
            snapshot = json.loads(raw)
            observations = track_candidates(members,
                normalize_tracking_quotes(snapshot['rows']), fetched_at.isoformat())
            sessions = collect_session_bundle([member['symbol'] for member in members])
            checked_at = datetime.now(timezone.utc)
            for row in observations:
                reference = sessions['references'].get(row['symbol'])
                row['quote_session_evidence'] = reference
                row['quote_session_check'] = evaluate_quote_session(
                    row['symbol'], row['current_price'], reference, checked_at,
                    documents=sessions['documents'])
                row['signal_blocked'] = row['signal_blocked'] or not row['quote_session_check']['passed']
            # A per-run envelope preserves the exact provider snapshot while
            # avoiding the legacy document upsert refreshing historical evidence.
            evidence = json.dumps({'scope': 'daily candidate tracking',
                'run_id': str(run_id), 'fetched_at': fetched_at.isoformat(),
                'snapshot_sha256': hashlib.sha256(raw).hexdigest(),
                'snapshot_json': raw.decode('utf-8'), 'quote_session_bundle': sessions}, sort_keys=True).encode('utf-8')
            archive = archive_snapshot(settings.evidence_directory, evidence)
            source_id = _store_document(connection, source_name=source[0],
                source_url=source[1], parser_version=source[2], published_at=None,
                fetched_at=fetched_at, raw_payload=evidence, local_path=str(archive),
                metadata={'scope': 'daily candidate tracking', 'run_id': str(run_id),
                          'snapshot_sha256': hashlib.sha256(raw).hexdigest(),
                          'candidate_count': len(members),
                          'quote_session_documents': sessions['documents']})
            store_tracking_observations(connection, run_id, source_id, observations)
            for row in observations:
                if row['current_price'] is None:
                    continue
                verified = row['quote_status'] == 'matched' and row['quote_session_check']['passed']
                metadata = {'automatic_cross_source_verification': verified,
                    'verification_method': 'tencent_all_market_price_plus_sina_snapshot',
                    'market_snapshot_source_id': str(source_id),
                    'per_symbol_price_evidence': row['price_cross_check'],
                    'tracking_run_id': str(run_id),
                    'quote_session_evidence': row['quote_session_evidence']}
                connection.execute("""INSERT INTO data_points
                    (data_point_id,symbol,field_name,period_label,value,unit,source_id,
                     validation_status,human_reviewed,metadata)
                    VALUES (%s,%s,'current_price',%s,%s,'CNY/share',%s,%s,false,%s::jsonb)""",
                    (uuid.uuid4(), row['symbol'], fetched_at.strftime('%Y-%m-%d %H:%M'),
                     row['current_price'], source_id, 'verified' if verified else 'pending',
                     json.dumps(metadata)))
            result = {'candidate_count': len(observations),
                      'blocked_count': sum(row['signal_blocked'] for row in observations),
                      'quote_session_blocked_count': sum(not row['quote_session_check']['passed'] for row in observations),
                      'quote_session_request_failures': sessions['request_failures']}
            end_run(connection, run_id, 'succeeded', result)
            connection.commit()
        except Exception as error:
            record_failed_run(connection, run_id, 'track-candidates', {'error': str(error)})
            connection.commit()
            raise
    return dict(result, status='succeeded', run_id=str(run_id))
