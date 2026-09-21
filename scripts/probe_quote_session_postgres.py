"""Exercise staged shared-source export on PostgreSQL temporary tables only."""
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

from value_investment_agent.db import connect, begin_run, end_run, _store_document
from value_investment_agent.settings import get_settings


def main():
    stage = Path(__file__).resolve().parent
    manifest = json.loads((stage / 'manifest.json').read_text())
    entry = next(row for row in manifest['files'] if row['name'] == 'candidate_tracking.py')
    path = stage / entry['name']
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry['new_sha256']:
        raise ValueError('Staged export module hash mismatch')
    spec = importlib.util.spec_from_file_location('staged_candidate_tracking', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = (stage / 'bundle.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != 'f1df713b937b540bd993bc433fa3bd9fd92942ce7892b2ae3c2e31c47556c0fe':
        raise ValueError('Actual quote bundle hash changed')
    bundle = json.loads(raw)
    now = datetime.now(timezone.utc)
    with connect(get_settings().database_url) as db:
        db.execute("SET lock_timeout='3s'")
        db.execute("SET statement_timeout='20s'")
        for table in ('task_runs', 'raw_documents', 'candidate_tracking_observations'):
            db.execute('CREATE TEMP TABLE ' + table + ' (LIKE public.' + table + ' INCLUDING ALL)')
        run = begin_run(db, 'track-candidates')
        source = _store_document(db, source_name='quote-session-isolated-probe',
            source_url='internal://quote-session-isolated-probe', published_at=None,
            fetched_at=now, parser_version='shared-session-probe-v1', raw_payload=raw,
            metadata={'quote_session_documents': bundle['documents']})
        _store_document(db, source_name='unrelated-probe-document',
            source_url='internal://unrelated-probe', published_at=None, fetched_at=now,
            parser_version='probe-v1', raw_payload=b'unrelated',
            metadata={'quote_session_documents': {'must_not_export': {'wrong_source': True}}})
        observations = [{'symbol': symbol, 'membership': {'symbol': symbol},
            'quote_as_of': now.isoformat(), 'quote_status': 'matched', 'signal_blocked': True,
            'quote_session_evidence': reference, 'current_price': None}
            for symbol, reference in bundle['references'].items()]
        module.store_tracking_observations(db, run, source, observations)
        end_run(db, run, 'succeeded', {'probe': True})
        exported = module.export_tracking_observations(db)
        assert exported['quote_session_documents'] == bundle['documents']
        assert len(exported['candidate_tracking']) == 3
        assert all(row['source_id'] == str(source) for row in exported['candidate_tracking'])
        assert all(row['signal_blocked'] is True for row in exported['candidate_tracking'])
        assert all(row['quote_session_evidence'] == bundle['references'][row['symbol']]
                   for row in exported['candidate_tracking'])
        second = begin_run(db, 'track-candidates')
        end_run(db, second, 'failed', {'probe': 'no fallback'})
        assert module.export_tracking_observations(db) == {'candidate_tracking': []}
        db.rollback()
        assert db.execute('SELECT count(*) AS n FROM public.task_runs WHERE run_id=ANY(%s::uuid[])',
                          ([str(run), str(second)],)).fetchone()['n'] == 0
        assert db.execute('SELECT count(*) AS n FROM public.raw_documents WHERE document_id=%s',
                          (source,)).fetchone()['n'] == 0
        db.rollback()
    print(json.dumps({'postgres_probe': 'passed', 'companies': 3,
        'shared_documents': len(bundle['documents']), 'unrelated_source_excluded': True,
        'failed_latest_run_does_not_fall_back': True, 'temporary_writes_rolled_back': True,
        'staged_candidate_tracking_sha256': entry['new_sha256'],
        'financial_or_strategy_approval': False}))


if __name__ == '__main__':
    main()
