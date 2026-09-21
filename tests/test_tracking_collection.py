import json
import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from value_investment_agent import tracking_collection as collection


class Connection:
    def __init__(self):
        self.commits = 0
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def commit(self):
        self.commits += 1

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return SimpleNamespace(fetchall=lambda: [{'symbol': '000333', 'initial_score': '60'}])


def setup(monkeypatch, tmp_path, *, fail=False):
    db = Connection()
    events = []
    monkeypatch.setattr(collection, 'connect', lambda url: db)
    monkeypatch.setattr(collection, 'begin_run', lambda *args: 'run')
    def store_document(*args, **kwargs):
        envelope = json.loads(kwargs['raw_payload'])
        assert envelope['run_id'] == 'run'
        assert envelope['snapshot_sha256'] == hashlib.sha256(envelope['snapshot_json'].encode('utf-8')).hexdigest()
        assert kwargs['metadata']['snapshot_sha256'] == envelope['snapshot_sha256']
        assert envelope['fetched_at'] == kwargs['fetched_at'].isoformat()
        return 'source'
    monkeypatch.setattr(collection, '_store_document', store_document)
    monkeypatch.setattr(collection, 'archive_snapshot', lambda *args: tmp_path / 'snapshot.json')
    monkeypatch.setattr(collection, 'store_tracking_observations',
                        lambda *args: events.append(('rows', args[-1])))
    monkeypatch.setattr(collection, 'end_run', lambda *args: events.append(('success', args[-1])))
    monkeypatch.setattr(collection, 'record_failed_run', lambda *args: events.append(('failed', args[-1])))
    monkeypatch.setattr(collection, 'collect_session_bundle', lambda symbols: {
        'documents': {'shared': {'test_only': True}},
        'references': {symbol: {'symbol': symbol, 'document_refs': {'test_only': True}} for symbol in symbols},
        'request_failures': []})
    # This test isolates storage wiring; raw-date validation has dedicated source replay tests.
    monkeypatch.setattr(collection, 'evaluate_quote_session', lambda *args, **kwargs: {'passed': True})

    def fetch(**kwargs):
        assert db.commits == 2
        assert kwargs == {'include_industry': False}
        if fail:
            raise RuntimeError('provider unavailable')
        raw = json.dumps({'rows': [{'symbol': '000333', 'current_price': '100',
            'pe': '50', 'price_cross_check': {'status': 'matched',
                'tencent_price': '100', 'sina_price': '100', 'sina_url': 'https://example.test'}}]}).encode()
        return [], {}, [], raw, datetime.now(timezone.utc), ('provider', 'https://example.test', 'v1')

    settings = SimpleNamespace(database_url='unused', evidence_directory=tmp_path)
    return db, events, settings, SimpleNamespace(fetch=fetch)


def test_daily_collection_retains_high_pe_member_and_writes_verified_price(monkeypatch, tmp_path):
    db, events, settings, adapter = setup(monkeypatch, tmp_path)
    result = collection.collect_candidate_quotes(settings, adapter)
    assert result['candidate_count'] == 1 and result['blocked_count'] == 0
    assert events[0][1][0]['membership']['initial_score'] == '60'
    assert events[0][1][0]['pe'] == '50'
    writes = [(sql, params) for sql, params in db.calls if 'INSERT' in sql]
    assert len(writes) == 1 and 'data_points' in writes[0][0]
    assert writes[0][1][-2] == 'verified'
    assert json.loads(writes[0][1][-1])['quote_session_evidence']['symbol'] == '000333'
    assert 'raw_base64' not in writes[0][1][-1]
    assert not any('DELETE' in sql or 'UPDATE market_screen' in sql for sql, _ in db.calls)
    assert db.commits == 3


def test_dated_quote_failure_keeps_company_but_never_writes_verified_price(monkeypatch, tmp_path):
    db, events, settings, adapter = setup(monkeypatch, tmp_path)
    monkeypatch.setattr(collection, 'evaluate_quote_session',
                        lambda *args, **kwargs: {'passed': False, 'status': 'intraday_quote'})
    result = collection.collect_candidate_quotes(settings, adapter)
    assert result['candidate_count'] == result['blocked_count'] == result['quote_session_blocked_count'] == 1
    writes = [params for sql, params in db.calls if 'INSERT INTO data_points' in sql]
    assert writes[0][-2] == 'pending'
    assert not json.loads(writes[0][-1])['automatic_cross_source_verification']


def test_provider_failure_is_audited_without_price_writes(monkeypatch, tmp_path):
    db, events, settings, adapter = setup(monkeypatch, tmp_path, fail=True)
    with pytest.raises(RuntimeError, match='provider unavailable'):
        collection.collect_candidate_quotes(settings, adapter)
    assert events == [('failed', {'error': 'provider unavailable'})]
    assert not any('INSERT' in sql for sql, _ in db.calls)
    assert db.commits == 3
