from datetime import datetime, timezone
import hashlib
import json
import pytest
from value_investment_agent.infrastructure.filings.disclosure_availability import indexed_disclosure_availability


def index():
    return dict(url='https://www.cninfo.com.cn/new/hisAnnouncement/query', announcements=[dict(
        announcementId='123', secCode='600887', adjunctUrl='finalpage/2026-08-27/123.PDF',
        announcementTime=int(datetime(2026, 8, 26, 16, tzinfo=timezone.utc).timestamp() * 1000))])


def call(value):
    return indexed_disclosure_availability(value, symbol='600887', source_id='cninfo:123',
                                           source_url='https://static.cninfo.com.cn/finalpage/2026-08-27/123.PDF')


def test_date_precision_is_conservative_not_intraday_proof():
    result = call(index())
    assert result['disclosure_date'] == '2026-08-27'
    assert result['available_from'] == '2026-08-28T00:00:00+08:00'
    assert result['timestamp_precision'] == 'DATE_ONLY'
    assert not result['intraday_publication_proven']
    assert not result['independent_historical_capture_proven']


@pytest.mark.parametrize('fault', ['provider', 'symbol', 'url', 'duplicate', 'missing', 'epoch'])
def test_index_mismatch_fails_closed(fault):
    value = index()
    if fault == 'provider': value['url'] = 'https://example.test/'
    if fault == 'symbol': value['announcements'][0]['secCode'] = '000333'
    if fault == 'url': value['announcements'][0]['adjunctUrl'] = 'other.pdf'
    if fault == 'duplicate': value['announcements'] *= 2
    if fault == 'missing': value['announcements'] = []
    if fault == 'epoch': value['announcements'][0]['announcementTime'] = True
    with pytest.raises(ValueError):
        call(value)


def test_reconstruction_separates_public_date_from_later_review(tmp_path, monkeypatch):
    import value_investment_agent.application.historical_validation.reconstructed_equity_input as service
    from test_bound_valuation_step import result
    original_valuation = json.loads(result().to_json())
    monkeypatch.setattr(service, 'load_existing_workbench_for_presentation',
                        lambda **kwargs: {'research': {'valuation': original_valuation}})
    fact = dict(fact_name='start_book_equity', value='100', unit='CNY', period='2026-06-30',
        source_id='cninfo:123', source_url='https://static.cninfo.com.cn/finalpage/2026-08-27/123.PDF',
        source_file_hash='a' * 64, physical_page=6, available_at='2026-09-30T16:00:00+00:00')
    monkeypatch.setattr(service, 'replay_residual_income_input', lambda **kwargs:
        dict(status='ARITHMETIC_MATCH', primary_numeric_review={'facts': [fact]}))
    value = index()
    value['announcements'][0]['secCode'] = original_valuation['symbol']
    path = tmp_path / 'index.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    args = dict(root=tmp_path, workbench_path=tmp_path / 'ignored.json', workbench_sha256='b' * 64,
        arithmetic_path=tmp_path / 'ignored-input.json', arithmetic_sha256='c' * 64,
        index_path=path, index_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        cutoffs=[datetime.fromisoformat('2026-08-27T15:00:00+08:00'),
                 datetime.fromisoformat('2026-08-28T00:00:00+08:00')])
    reconstructed = service.reconstruct_equity_inputs(**args)
    assert reconstructed['cutoffs'][0]['eligible_facts'] == []
    eligible = reconstructed['cutoffs'][1]['eligible_facts'][0]
    assert eligible['original_review_available_at'] == fact['available_at']
    assert not reconstructed['financial_gate_admitted']
    assert not reconstructed['assumptions_historically_registered']
    assert not reconstructed['strict_pit_admitted']
    path.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='index hash mismatch'):
        service.reconstruct_equity_inputs(**args)
