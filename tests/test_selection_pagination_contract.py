from datetime import datetime, timezone
import pytest
from value_investment_agent.application.discovery.dual_strategy_selection import build_dual_strategy_selection


def test_independent_candidate_pagination(tmp_path):
    calls = []
    def value(**kwargs):
        return dict(action='no_order', items=[dict(symbol=str(i), research_priority_eligible=i % 2 == 0) for i in range(80)])
    def hotspot(**kwargs):
        calls.append(kwargs['limit'])
        return dict(action='no_order', items=[dict(symbol=str(i), selection_status='EXCLUDED' if i == 0 else 'UNKNOWN') for i in range(30)])
    result = build_dual_strategy_selection(root=tmp_path, now=datetime.now(timezone.utc),
        value_selector=value, hotspot_selector=hotspot, limit=10, value_offset=10, hotspot_offset=20)
    assert result['value']['pagination'] == dict(offset=10, limit=10, total=40)
    assert result['value']['items'][0]['symbol'] == '20'
    assert result['hotspot']['pagination']['total'] == 29
    assert len(result['hotspot']['items']) == 9
    assert calls == [30]


def test_api_strategy_isolation_and_broken_research(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api.app import create_app
    from value_investment_agent.application.research import value_research_analysis as research
    from value_investment_agent.application.discovery import value_candidate_selection as value
    from value_investment_agent.application.hotspot import candidate_selection as hotspot
    monkeypatch.setattr(value, 'select_current_value_candidates', lambda **kw: dict(action='no_order', items=[dict(symbol='600519', name='value', research_priority_eligible=True)], quote_date='2026-10-23'))
    monkeypatch.setattr(hotspot, 'select_current_hotspot_candidates', lambda **kw: dict(action='no_order', items=[dict(symbol='600519', name='hotspot', selection_status='SELECTED')], trade_date='2026-10-23'))
    monkeypatch.setattr(research, 'load_current_value_research_analysis', lambda **kw: None)
    monkeypatch.setattr(value, 'load_current_public_candidate_research', lambda **kw: None)
    client = TestClient(create_app(tmp_path))
    v = client.get('/api/v1/decisions/600519?strategy=value').json()
    h = client.get('/api/v1/decisions/600519?strategy=hotspot').json()
    assert v['decision']['strategy'] == 'CORE_VALUE'
    assert h['decision']['strategy'] == 'HOTSPOT_SATELLITE'
    assert v['selection_candidate']['name'] == 'value'
    assert h['selection_candidate']['name'] == 'hotspot'
    assert h['selection_candidate']['trade_date'] == '2026-10-23'
    def broken(**kw):
        raise ValueError('damaged registry')
    monkeypatch.setattr(research, 'load_current_value_research_analysis', broken)
    broken_value = client.get('/api/v1/decisions/600519?strategy=value').json()
    assert broken_value['decision'] is None
    assert 'selection_candidate' not in broken_value
    assert client.get('/api/v1/decisions/600519?strategy=hotspot').json()['decision']['action'] == 'no_order'


def test_api_source_failure_is_not_zero(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api.app import create_app
    from value_investment_agent.application.discovery import value_candidate_selection as value
    from value_investment_agent.application.hotspot import candidate_selection as hotspot
    monkeypatch.setattr(value, 'select_current_value_candidates', lambda **kw: dict(action='no_order', items=[], data_status='SOURCE_REVALIDATION_FAILED'))
    monkeypatch.setattr(hotspot, 'select_current_hotspot_candidates', lambda **kw: dict(action='no_order', items=[], status='RESEARCH_SELECTION_REPLAYED'))
    result = TestClient(create_app(tmp_path)).get('/api/v1/strategy-selection?limit=10').json()
    assert result['value']['pagination']['total'] is None
    assert result['hotspot']['pagination']['total'] == 0


@pytest.mark.parametrize('mode,expected', [
    ('valid', 'CONDITIONAL_RESEARCH'), ('missing', 'SCREENING_ONLY'),
    ('broken', 'RESEARCH_SOURCE_UNAVAILABLE'), ('identity', 'RESEARCH_SOURCE_UNAVAILABLE'),
    ('authority', 'RESEARCH_SOURCE_UNAVAILABLE'), ('valuation_missing', 'RESEARCH_SOURCE_UNAVAILABLE'),
])
def test_existing_research_summary_projection(tmp_path, monkeypatch, mode, expected):
    from value_investment_agent.application.discovery import value_candidate_selection as value
    from value_investment_agent.application.research import value_research_analysis as research
    rows = [dict(symbol=str(i), research_priority_eligible=True) for i in range(3)]
    monkeypatch.setattr(value, 'select_current_value_candidates', lambda **kw: dict(action='no_order', items=rows))
    calls = []
    valuation = {'bear_value': '10', 'base_value': '20', 'bull_value': '30', 'confidence': 'LOW'}
    def loader(**kw):
        calls.append(kw['symbol'])
        if mode == 'broken':
            raise ValueError('invalid source')
        if mode == 'missing':
            return None
        data = dict(symbol='other' if mode == 'identity' else kw['symbol'],
                    action='order' if mode == 'authority' else 'no_order',
                    valuation=valuation, research_as_of='2026-10-23',
                    valuation_date='2026-10-22', counter_evidence=['risk'], blockers=['unapproved'])
        if mode == 'valuation_missing':
            data.pop('valuation')
        return data
    monkeypatch.setattr(research, 'load_current_value_research_analysis', loader)
    result = build_dual_strategy_selection(root=tmp_path, now=datetime.now(timezone.utc),
        limit=1, value_offset=1, hotspot_selector=lambda **kw: dict(action='no_order', items=[]))
    assert calls == ['1']
    lane = result['value']
    summary = lane['items'][0]['research_summary']
    assert summary['status'] == expected
    assert summary['action'] == 'no_order'
    assert summary['valuation'] == (valuation if mode == 'valid' else None)
    assert lane['shortlist'] == lane['items']
    assert lane['pagination']['total'] == 3
    assert all('research_summary' not in row for row in rows)
    if mode == 'valid':
        assert summary['research_as_of'] == '2026-10-23'
        assert summary['counter_evidence'] == ['risk']
        assert summary['blockers'] == ['unapproved']


def test_custom_selector_never_loads_research(tmp_path, monkeypatch):
    from value_investment_agent.application.research import value_research_analysis as research
    def forbidden(**kw):
        pytest.fail('custom selector must not load research')
    monkeypatch.setattr(research, 'load_current_value_research_analysis', forbidden)
    result = build_dual_strategy_selection(root=tmp_path, now=datetime.now(timezone.utc),
        value_selector=lambda **kw: dict(action='no_order', items=[dict(symbol='600519', research_priority_eligible=True)]),
        hotspot_selector=lambda **kw: dict(action='no_order', items=[]))
    assert 'research_summary' not in result['value']['items'][0]
