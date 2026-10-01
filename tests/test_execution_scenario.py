import hashlib
import json
import pytest
from value_investment_agent.application.historical_validation.execution_scenario import replay_execution_scenario


def scenario():
    return dict(schema_version='shared-execution-engineering-input-v1', scope='SYNTHETIC_ENGINEERING_FIXTURE',
        symbol='600887', action='no_order', initial_cash_cny='10000', sessions=[
            dict(date='2025-06-02', open='10', close='10', execution_ready=True,
                 price_limit_down='9', price_limit_up='11'),
            dict(date='2025-06-03', open='10', close='10', execution_ready=True,
                 price_limit_down='9', price_limit_up='11')], decisions={
                '2025-06-02': dict(state='proposed_entry', decision_id='fixture-entry', quantity=100,
                    action='no_order', trade_approved=False, live_eligible=False, execution_terms=dict(
                        version='next-session-bounded-order-v1', valid_session='2025-06-03',
                        liquidity_as_of='2025-06-02', basis_id='synthetic-constraint-test',
                        limit_price='11', cash_budget_cny='2000', liquidity_budget_cny='5000', slippage_bps='10'))})


@pytest.mark.parametrize('fault', ['none', 'future-fees', 'live', 'unbounded'])
def test_existing_engine_is_explicitly_synthetic_and_bounded(tmp_path, fault):
    value = scenario()
    if fault == 'future-fees': value['sessions'][1]['date'] = '2026-06-03'
    if fault == 'live': value['decisions']['2025-06-02']['trade_approved'] = True
    if fault == 'unbounded': del value['decisions']['2025-06-02']['execution_terms']
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    args = dict(root=tmp_path, path=path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), symbol='600887')
    if fault != 'none':
        with pytest.raises(ValueError): replay_execution_scenario(**args)
        return
    output = replay_execution_scenario(**args)
    assert output['final_account']['shares'] == 100
    assert output['final_account']['cash'] == '8993.99'
    assert not output['historical_execution_validated']
    assert output['execution_marker']['simulation_only']
    assert all(row['execution_marker']['simulation_only'] for row in output['journal'])
    assert output['journal'][1]['fill']['execution_marker']['action'] == 'no_order'
    assert not output['performance_claim_allowed']


@pytest.mark.parametrize('fault', ['suspension', 'limit', 'liquidity'])
def test_shared_adapter_preserves_execution_rejections(tmp_path, fault):
    value = scenario()
    if fault == 'suspension': value['sessions'][1]['execution_ready'] = False
    if fault == 'limit': value['sessions'][1]['open'] = '11'
    if fault == 'liquidity':
        value['decisions']['2025-06-02']['execution_terms']['liquidity_budget_cny'] = '500'
    path = tmp_path / 'rejected.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    output = replay_execution_scenario(root=tmp_path, path=path,
        expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), symbol='600887')
    assert output['final_account']['shares'] == 0
    assert output['journal'][1]['fill'] is None
    assert output['journal'][1]['rejected_order_reason']
