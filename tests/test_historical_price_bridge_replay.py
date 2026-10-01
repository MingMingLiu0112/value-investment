from datetime import datetime
import hashlib
import json
import pytest
from value_investment_agent.application.historical_validation import historical_price_bridge as service
from value_investment_agent.quote_snapshot import QuoteSnapshot
from test_bound_valuation_step import result


def test_quote_capture_and_original_integrity_are_separate_gates(tmp_path, monkeypatch):
    valuation = json.loads(result().to_json())
    monkeypatch.setattr(service, 'load_existing_workbench_for_presentation',
                        lambda **kwargs: {'generated_at': '2026-10-01T00:00:00+00:00',
                            'research': {'valuation': valuation, 'source_records': [],
                                'dependency_view': {'observed_at': '2026-09-30T00:00:00+00:00'}}})
    quote_path = tmp_path / 'quote.json'
    quote_path.write_text(json.dumps({'finished_at': '2026-09-23T00:56:34+00:00'}), encoding='utf-8')
    digest = hashlib.sha256(quote_path.read_bytes()).hexdigest()
    monkeypatch.setattr(service, 'quote_snapshot_from_bundle_file', lambda *args, **kwargs:
        QuoteSnapshot(symbol=valuation['symbol'], quote_date=None, current_price=None,
                      status='PENDING_EXTERNAL_DATA', evidence_refs=[], blockers=['quote missing']))
    monkeypatch.setattr(service, 'audit_event_evidence', lambda **kwargs:
                        {'evidence_integrity_verified': False, 'status': 'NOT_READY'})
    monkeypatch.setattr(service, 'evaluate_model_validity',
                        lambda **kwargs: pytest.fail('must not evaluate corrupt evidence'))
    args = dict(root=tmp_path, workbench_path=tmp_path / 'unused', workbench_sha256='a'*64,
        quote_path=quote_path, quote_sha256=digest, scan_path=tmp_path / 'unused-scan',
        scan_sha256='b'*64, cutoffs=[datetime.fromisoformat('2026-09-22T15:00:00+08:00'),
                                   datetime.fromisoformat('2026-09-23T09:00:00+08:00')])
    replay = service.replay_historical_bridge(**args)
    assert all(row['valuation'] is None for row in replay['rows'])
    assert all(not row['valuation_observed'] for row in replay['rows'])
    assert replay['rows'][0]['quote'] is None
    assert replay['rows'][1]['quote'] is not None
    assert all(row['bridge'] is None and row['suggested_state'] == 'NOT_READY' for row in replay['rows'])
    assert not replay['strict_pit_admitted']
    assert not replay['historical_execution_validated']
    args['quote_sha256'] = 'c'*64
    with pytest.raises(ValueError, match='quote hash mismatch'):
        service.replay_historical_bridge(**args)
