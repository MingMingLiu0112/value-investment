from datetime import datetime, timezone

import pytest

from value_investment_agent.application.discovery.dual_strategy_selection import build_dual_strategy_selection

NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)


def lane(**kwargs):
    return dict(action='no_order', status='SOURCE_REPLAYED', items=[], shortlist=[],
                formal_eligibility=False, trade_eligible=False)


def test_external_gap_in_one_lane_does_not_block_other(tmp_path):
    def unavailable(**kwargs):
        raise OSError('private path must not be exposed')
    result = build_dual_strategy_selection(root=tmp_path, now=NOW,
        value_selector=unavailable, hotspot_selector=lane)
    assert result['value']['status'] == 'SOURCE_OR_SELECTION_UNAVAILABLE'
    assert result['hotspot']['status'] == 'SOURCE_REPLAYED'
    assert result['formal_eligibility'] is result['trade_eligible'] is False
    assert 'private path' not in str(result)


@pytest.mark.parametrize('bad', [
    {'action': 'order'}, {'action': 'no_order', 'formal_eligibility': True},
    {'action': 'no_order', 'items': [{'trade_eligible': True}]},
    {'action': 'no_order', 'items': [{'action_eligibility': True}]},
    {'action': 'no_order', 'items': [{'portfolio_eligibility': 1}]},
    {'action': 'no_order', 'items': [{'buy_eligible': 'false'}]},
    {'action': 'no_order', 'score': float('nan')},
])
def test_selection_cannot_promote_authority_or_invalid_contract(tmp_path, bad):
    result = build_dual_strategy_selection(root=tmp_path, now=NOW,
        value_selector=lambda **kw: bad, hotspot_selector=lane)
    assert result['value']['status'] == 'SOURCE_OR_SELECTION_UNAVAILABLE'
    assert result['strategy_validation'] == 'NOT_PROVEN'


def test_identity_is_stable_and_inputs_are_bounded(tmp_path):
    first = build_dual_strategy_selection(root=tmp_path, now=NOW, value_selector=lane, hotspot_selector=lane)
    second = build_dual_strategy_selection(root=tmp_path, now=NOW, value_selector=lane, hotspot_selector=lane)
    assert first == second
    with pytest.raises(ValueError):
        build_dual_strategy_selection(root=tmp_path, now=NOW.replace(tzinfo=None), value_selector=lane, hotspot_selector=lane)


def test_full_universe_is_not_sent_to_web_but_coverage_is_preserved(tmp_path):
    source = lane()
    source.update(items=[{'symbol': str(i)} for i in range(5577)],
                  shortlist=[{'symbol': '600519'}],
                  coverage={'observation_count': 50063, 'universe_count': 5577})
    result = build_dual_strategy_selection(root=tmp_path, now=NOW,
        value_selector=lambda **kw: source, hotspot_selector=lane)
    assert result['value']['items'] == [{'symbol': '600519'}]
    assert result['value']['coverage']['universe_count'] == 5577
    assert len(source['items']) == 5577


def test_web_route_is_read_only_and_contains_no_private_account_data(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api.app import create_app
    from value_investment_agent.application.discovery import dual_strategy_selection as selection
    result = build_dual_strategy_selection(root=tmp_path, now=NOW,
        value_selector=lane, hotspot_selector=lane)
    monkeypatch.setattr(selection, 'build_dual_strategy_selection', lambda **kw: result)
    response = TestClient(create_app(tmp_path)).get('/api/v1/strategy-selection')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['personal_risk_evaluated'] is False
    assert not list(tmp_path.rglob('*.jsonl'))
