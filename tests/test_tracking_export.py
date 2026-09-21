from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from value_investment_agent.candidate_tracking import export_tracking_observations


class Connection:
    def __init__(self, run, rows=()):
        self.run, self.rows, self.calls = run, rows, []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if 'FROM task_runs' in sql:
            assert "task_name = 'track-candidates'" in sql
            assert 'ORDER BY started_at DESC' in sql
            assert "status = 'succeeded'" not in sql
            return SimpleNamespace(fetchone=lambda: self.run)
        assert params == (self.run['run_id'],)
        assert 'WHERE run_id = %s' in sql
        return SimpleNamespace(fetchall=lambda: self.rows)


def test_not_enabled_preserves_legacy_export_without_accessing_new_table():
    db = Connection(None)
    assert export_tracking_observations(db) == {}
    assert len(db.calls) == 1


@pytest.mark.parametrize('status', ['failed', 'running'])
def test_new_unsuccessful_run_blocks_instead_of_falling_back(status):
    db = Connection({'run_id': 'new', 'status': status})
    assert export_tracking_observations(db) == {'candidate_tracking': []}
    assert len(db.calls) == 1


def test_export_uses_run_identity_and_keeps_membership_evidence():
    row = {'symbol': '000333', 'source_id': 'new-source',
           'quote_as_of': datetime(2026, 9, 8, 8, tzinfo=timezone.utc),
           'quote_status': 'missing_quote', 'signal_blocked': True,
           'observation': {'symbol': 'bad', 'source_id': 'old-source',
                           'signal_blocked': False, 'current_price': None,
                           'membership': {'symbol': '000333', 'initial_score': '60'}}}
    db = Connection({'run_id': 'new', 'status': 'succeeded'}, [row])
    exported = export_tracking_observations(db)['candidate_tracking'][0]
    assert exported['symbol'] == '000333'
    assert exported['source_id'] == 'new-source'
    assert exported['signal_blocked'] is True
    assert exported['quote_as_of'] == '2026-09-08T08:00:00+00:00'
    assert exported['membership']['initial_score'] == '60'
    assert row['observation']['source_id'] == 'old-source'


def test_empty_successful_run_does_not_disable_tracking_gate():
    db = Connection({'run_id': 'new', 'status': 'succeeded'})
    assert export_tracking_observations(db) == {'candidate_tracking': []}


def test_shared_documents_are_exported_once_from_the_exact_observation_source():
    source = '00000000-0000-0000-0000-000000000001'
    rows = [{'symbol': symbol, 'source_id': source, 'quote_as_of': datetime.now(timezone.utc),
             'quote_status': 'matched', 'signal_blocked': True,
             'observation': {'quote_session_evidence': {'symbol': symbol, 'document_refs': {}}}}
            for symbol in ('000333', '600519')]
    class DocumentsConnection(Connection):
        def execute(self, sql, params=None):
            if 'FROM raw_documents' in sql:
                self.calls.append((sql, params))
                assert params == ([source],)
                return SimpleNamespace(fetchall=lambda: [{'document_id': source,
                    'metadata': {'quote_session_documents': {'document': {'raw_base64': 'test'}}}}])
            return super().execute(sql, params)
    db = DocumentsConnection({'run_id': 'new', 'status': 'succeeded'}, rows)
    exported = export_tracking_observations(db)
    assert len(exported['candidate_tracking']) == 2
    assert exported['quote_session_documents'] == {'document': {'raw_base64': 'test'}}
    assert len([sql for sql, _ in db.calls if 'FROM raw_documents' in sql]) == 1
