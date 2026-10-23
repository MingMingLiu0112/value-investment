from fastapi.testclient import TestClient
from value_investment_agent.presentation.web_api.app import create_app
from value_investment_agent.application.decision import value_price_policy
import json
import pytest
from test_pending_candidate_supplement import registered


def test_missing_review_routes_fail_closed_without_private_auth(tmp_path):
    client = TestClient(create_app(root=tmp_path))
    for route in ("value-policy-review/600887", "hotspot-replay-review"):
        response = client.get("/api/v1/" + route)
        assert response.status_code == 409
        assert response.json()["action"] == "no_order"
    assert not list(tmp_path.rglob("*.json"))


def test_simulated_journey_route_uses_no_private_account_and_removes_journal(tmp_path, monkeypatch):
    from value_investment_agent.application.portfolio import private_portfolio_service
    def forbidden(*args, **kwargs):
        raise AssertionError('Simulation must not resolve the user account')
    monkeypatch.setattr(private_portfolio_service, 'resolve_private_root', forbidden)
    response = TestClient(create_app(root=tmp_path)).get('/api/v1/simulated-trade-journey')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    body = response.json()
    assert body['namespace'] == 'SIMULATED'
    assert body['actual_account_used'] is body['strategy_validated'] is False
    assert all(body['checks'].values())
    assert not list(tmp_path.rglob('*.jsonl'))


def _source_manual_payload(symbol='600887'):
    return dict(confirmed_hypothetical=True, initial_cash_cny='100000', expected_candidates=[dict(
        symbol=symbol, candidate_binding=dict(path='runtime/TEST_ONLY/candidate.json', sha256='a' * 64),
        research_version='TEST_ONLY')], manual_fills=[dict(
        fill=dict(transaction_id='SIMULATED-API-EXPLICIT', side='BUY', sleeve='CORE_VALUE',
            symbol=symbol, exchange='SSE', quantity='100', price_cny='10', fees_cny='5',
            trade_date='2026-10-23', trading_unit='100'))])


def test_source_mode_missing_inputs_is_not_the_legacy_positive_demo(tmp_path, monkeypatch):
    from value_investment_agent.application.portfolio import private_portfolio_service
    monkeypatch.setattr(private_portfolio_service, 'resolve_private_root',
        lambda *args, **kwargs: pytest.fail('public source mode must not resolve a real account'))
    response = TestClient(create_app(root=tmp_path)).get('/api/v1/simulated-trade-journey?mode=source_bound')
    assert response.status_code == 409 and response.headers['cache-control'] == 'no-store'
    assert response.json()['status'] == 'SOURCE_OR_REHEARSAL_UNAVAILABLE'
    assert response.json()['action'] == 'no_order' and 'steps' not in response.json()
    assert not list(tmp_path.rglob('*.jsonl'))


@pytest.mark.parametrize('failure', ['missing', 'source_drift'])
def test_bad_historical_action_binding_keeps_replay_independent_and_visible(tmp_path, monkeypatch, failure):
    from value_investment_agent.application.hotspot import replay_read_model
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/hotspot-replay-review-v1.json').write_text(json.dumps(dict(action='no_order',
        manifest_sha256='fixture', structure_manifest_sha256='fixture',
        historical_action_observation_binding=dict(path='runtime/missing.json', sha256='a' * 64))), encoding='utf-8')
    monkeypatch.setattr(replay_read_model, 'load_replay_summary', lambda **kwargs:
        dict(action='no_order', items=[], formal_eligibility=False))
    if failure == 'source_drift':
        from value_investment_agent.application.product import historical_action_lineage
        def changed_after_parsing(**kwargs):
            raise ValueError('Historical evidence changed during replay')
        monkeypatch.setattr(historical_action_lineage, 'load_historical_action_lineage', changed_after_parsing)
    result = TestClient(create_app(root=tmp_path)).get('/api/v1/hotspot-replay-review')
    assert result.status_code == 200
    assert result.json()['historical_action_lineage']['status'] == 'UNAVAILABLE'
    assert result.json()['formal_eligibility'] is False and result.json()['items'] == []


@pytest.mark.parametrize('failure', [ValueError, ArithmeticError])
def test_simulated_hotspot_source_failure_is_local_not_an_empty_replay(tmp_path, monkeypatch, failure):
    from value_investment_agent.application.hotspot import replay_read_model, simulated_lifecycle
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/hotspot-replay-review-v1.json').write_text(json.dumps(dict(action='no_order',
        manifest_sha256='fixture', structure_manifest_sha256='fixture',
        simulated_hotspot_lifecycle_receipt_binding=dict(path='runtime/missing.json', sha256='a' * 64))), encoding='utf-8')
    monkeypatch.setattr(replay_read_model, 'load_replay_summary', lambda **kwargs:
        dict(action='no_order', items=[], formal_eligibility=False))
    def unavailable(*args, **kwargs):
        raise failure('TEST_ONLY unverifiable sealed simulation')
    monkeypatch.setattr(simulated_lifecycle, 'load_simulated_hotspot_lifecycle', unavailable)
    response = TestClient(create_app(root=tmp_path)).get('/api/v1/hotspot-replay-review')
    assert response.status_code == 200
    assert response.json()['simulated_hotspot_lifecycle']['status'] == 'UNAVAILABLE'
    assert response.json()['formal_eligibility'] is False and response.json()['items'] == []


@pytest.mark.parametrize('mutation', [
    'no_confirmation', 'numeric_confirmation', 'empty_fills', 'too_many_fills',
    'actual_namespace', 'workspace', 'clock', 'approval', 'other_sleeve', 'other_symbol',
    'sell_session', 'nonfinite_price', 'numeric_quantity', 'no_expected_identity',
])
def test_source_manual_api_rejects_unsupported_scope_before_service(tmp_path, monkeypatch, mutation):
    from value_investment_agent.presentation.web_api import simulated_journey_routes as routes
    payload = _source_manual_payload()
    fill = payload['manual_fills'][0]['fill']
    if mutation == 'no_confirmation':
        payload.pop('confirmed_hypothetical')
    elif mutation == 'numeric_confirmation':
        payload['confirmed_hypothetical'] = 1
    elif mutation == 'empty_fills':
        payload['manual_fills'] = []
    elif mutation == 'too_many_fills':
        payload['manual_fills'] *= 5
    elif mutation == 'actual_namespace':
        payload['namespace'] = 'ACTUAL'
    elif mutation == 'workspace':
        payload['workspace_root'] = '../private'
    elif mutation == 'clock':
        payload['now'] = '2027-01-01T00:00:00Z'
    elif mutation == 'approval':
        fill['strategy_admitted'] = True
    elif mutation == 'other_sleeve':
        fill['sleeve'] = 'TACTICAL_HOTSPOT'
    elif mutation == 'other_symbol':
        fill['symbol'] = '000001'
    elif mutation == 'sell_session':
        fill['next_sell_session'] = '2026-10-24'
    elif mutation == 'nonfinite_price':
        fill['price_cny'] = 'NaN'
    elif mutation == 'no_expected_identity':
        payload.pop('expected_candidates')
    else:
        fill['quantity'] = 100
    monkeypatch.setattr(routes, 'run_source_bound_simulated_trade_journey',
        lambda *args, **kwargs: pytest.fail('request validation must precede the service'))
    response = TestClient(create_app(root=tmp_path)).post('/api/v1/simulated-trade-journey', json=payload)
    assert response.status_code == 422 and response.json()['action'] == 'no_order'
    assert not list(tmp_path.rglob('*.jsonl'))


def test_source_api_actual_use_case_requires_explicit_manual_request(registered, monkeypatch):
    from value_investment_agent.presentation.web_api import simulated_journey_routes as routes
    from value_investment_agent.application.portfolio import private_portfolio_service
    root, symbol, _, _ = registered
    actual = routes.run_source_bound_simulated_trade_journey
    # The isolated registered fixture has one company; production defaults to both registered samples.
    monkeypatch.setattr(routes, 'run_source_bound_simulated_trade_journey',
        lambda project, now, **kwargs: actual(project, now, **dict(kwargs, symbols=[symbol])))
    monkeypatch.setattr(private_portfolio_service, 'resolve_private_root',
        lambda *args, **kwargs: pytest.fail('source rehearsal must not consult private root'))
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    client = TestClient(create_app(root=root))
    read = client.get('/api/v1/simulated-trade-journey?mode=source_bound')
    assert read.status_code == 200, read.text
    assert read.json()['manual_rehearsal']['status'] == 'NOT_REQUESTED'
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    payload = _source_manual_payload(symbol)
    payload['expected_candidates'] = [dict(symbol=case['symbol'],
        candidate_binding=case['research']['candidate_binding'], research_version=case['research']['research_version'])
        for case in read.json()['cases']]
    rejected = client.post('/api/v1/simulated-trade-journey', json=_source_manual_payload(symbol))
    assert rejected.status_code == 409 and rejected.json()['status'] == 'RESEARCH_VERSION_CHANGED'
    assert not list(root.rglob('*.jsonl'))
    response = client.post('/api/v1/simulated-trade-journey', json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert response.headers['cache-control'] == 'no-store'
    assert body['position_guidance'] is None and body['personal_risk_evaluated'] is False
    assert body['cases'][0]['evaluation']['eligibility'] is False
    assert all(slot['outcome'] in {'WAIT', 'NO_ACTION'} for slot in body['cases'][0]['action_slots'])
    manual = body['manual_rehearsal']
    assert manual['actual_account_used'] is False
    assert manual['restart_equal'] and manual['temporary_journal_removed']
    assert manual['account_state']['cash_cny'] == '98995'
    assert manual['fills'][0]['fill']['next_sell_session'] == '2026-10-26'
    assert manual['fills'][0]['confirmation_idempotent'] is True
    assert manual['fills'][0]['original_entry_advisory_eligible'] is False
    assert not list(root.rglob('*.jsonl'))


def test_value_review_route_preserves_unapproved_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(value_price_policy, "load_value_policy_review", lambda *args: {
        "model_review": {"formal_eligibility": False},
        "preparation": {"registered": False, "draft_prices": {"BUY": None}}})
    result = TestClient(create_app(root=tmp_path)).get("/api/v1/value-policy-review/600887").json()
    assert result["action"] == "no_order"
    assert result["status"] == "RESEARCH_ONLY"
    assert result["preparation"]["registered"] is False


@pytest.mark.parametrize('scope', ['DESCRIPTIVE', 'ADMITTED'])
def test_retained_review_preserves_descriptive_scope_or_rejects(tmp_path, monkeypatch, scope):
    from value_investment_agent.application.hotspot import replay_read_model, retained_source_replay, strategy_execution_replay
    (tmp_path / 'config').mkdir()
    pins = dict(action='no_order', manifest_sha256='legacy', structure_manifest_sha256='structure',
                retained_manifest_binding=dict(path='runtime/TEST_ONLY.json', sha256='test'))
    (tmp_path / 'config/hotspot-replay-review-v1.json').write_text(json.dumps(pins), encoding='utf-8')
    monkeypatch.setattr(replay_read_model, 'load_replay_summary', lambda **kw:
        dict(action='no_order', formal_eligibility=False, items=[]))
    calls = []
    def retained(**kw):
        calls.append(kw)
        return dict(namespace='ACTUAL', scope=scope, action='no_order', formal_eligibility=False,
                    trade_count=None, strategy_validation='NOT_PROVEN', signal_event_count=161)
    monkeypatch.setattr(retained_source_replay, 'load_retained_replay_summary', retained)
    monkeypatch.setattr(strategy_execution_replay, 'build_strategy_execution_replay', lambda **kw: dict(
        schema_version='hotspot-strategy-execution-retrospective-v1', evaluated_at='TEST_ONLY',
        status='PARTIAL', metrics_scope='RULE_GENERATED_RETROSPECTIVE_EXECUTION_ASSUMPTIONS',
        summary={'strict_closed_trade_count': 0, 'assumed_state_closed_trade_count': 10},
        gaps=['DATED_STOCK_STATUS_MISSING'], costs={}, parameter_fingerprint='a' * 64,
        source_fingerprint='b' * 64, strategy_validation='NOT_PROVEN', formal_eligibility=False,
        action='no_order', results=[]))
    response = TestClient(create_app(root=tmp_path)).get('/api/v1/hotspot-replay-review')
    assert calls[0]['manifest_binding'] == pins['retained_manifest_binding']
    assert response.status_code == (200 if scope == 'DESCRIPTIVE' else 409)
    if scope == 'DESCRIPTIVE':
        result = response.json()
        assert result['formal_eligibility'] is False
        assert result['retained_validation']['trade_count'] is None
        assert result['retained_validation']['strategy_validation'] == 'NOT_PROVEN'
        assert result['retained_validation']['signal_event_count'] == 161
        assert result['execution_validation']['summary']['strict_closed_trade_count'] == 0
        assert result['execution_validation']['formal_eligibility'] is False
        assert result['execution_validation']['case_results'] == []
