from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from value_investment_agent.application.hotspot.quantitative_validation import build_economic_validation_draft
from value_investment_agent.domain.hotspot.quantitative_validation import evaluate_economic_validation_draft
from value_investment_agent.domain.execution.exchange_calendar import is_exchange_session, next_exchange_session


def fixture():
    """Arithmetic fixtures only; never real approval or market evidence."""
    draft = build_economic_validation_draft(now=datetime(2026, 10, 25, tzinfo=timezone.utc))
    draft['economic_policy'] = dict(minimum_excess_cash='0', minimum_excess_pool='0',
        maximum_drawdown='0.2', minimum_trades=5,
        uncertainty_method='SYNTHETIC_PAIRED_BOUND', minimum_excess_lower_bound='0',
        uncertainty_parameters={'fixture_only': True}, cost_evaluation='BASE_NET_WITH_0X_2X_DISCLOSURE')
    sessions, day = [], date(2026, 1, 5)
    while len(sessions) < 126:
        if is_exchange_session('SSE', day):
            sessions.append(day.isoformat())
        day += timedelta(days=1)
    blocks = [dict(sessions=sessions[i * 42:(i + 1) * 42],
        scope='PAIRED_SAME_POOL_PORTFOLIO_NET_OF_COST', strategy_net_return='0.1',
        cash_net_return='0', pool_net_return='0.05', excess_lower_bound='0.01',
        cost_returns={'0': '0.11', '1': '0.1', '2': '0.09'},
        maximum_drawdown='0.1', trade_count=8, uncertainty_method='SYNTHETIC_PAIRED_BOUND')
        for i in range(3)]
    for block in blocks:
        block['uncertainty_parameters'] = {'fixture_only': True}
    return draft, blocks


def test_complete_synthetic_economic_comparison_never_grants_real_admission():
    draft, blocks = fixture()
    before = deepcopy((draft, blocks))
    result = evaluate_economic_validation_draft(draft, blocks)
    assert result['economic_evaluation'] == 'PASS'
    assert result['status'] == 'NOT_ADMITTED'
    assert result['formal_eligibility'] is result['strict_oos_admitted'] is result['actual_sample_accepted'] is False
    assert result['action'] == 'no_order' and result['strategy_validation'] == 'NOT_PROVEN'
    assert before == (draft, blocks)


def test_candidate_policy_is_explicit_reasoned_and_unapproved():
    draft = build_economic_validation_draft(now=datetime(2026, 10, 25, tzinfo=timezone.utc))
    assert draft['economic_policy']['maximum_drawdown'] == '0.20'
    assert draft['economic_policy']['uncertainty_parameters']['block_length'] == 10
    assert draft['policy_rationale'] and 'not an industry standard' in draft['policy_rationale']['drawdown']
    assert draft['registered_at'] is None and draft['approval_status'] == 'NOT_APPROVED'
    result = evaluate_economic_validation_draft(draft, [])
    assert result['economic_evaluation'] == 'INSUFFICIENT_DATA'


def test_missing_policy_still_cannot_pass():
    draft, blocks = fixture()
    draft['economic_policy']['maximum_drawdown'] = None
    assert evaluate_economic_validation_draft(draft, blocks)['economic_evaluation'] == 'INSUFFICIENT_DATA'


def test_candidate_cost_stress_floor_is_executable():
    draft, blocks = fixture()
    draft['economic_policy']['cost_evaluation'] = 'BASE_NET_WITH_2X_CASH_FLOOR'
    blocks[0]['cost_returns']['2'] = '-0.01'
    assert evaluate_economic_validation_draft(draft, blocks)['economic_evaluation'] == 'FAIL'


def test_candidate_uncertainty_requires_full_window_not_each_short_block():
    draft, blocks = fixture()
    draft['economic_policy'] = build_economic_validation_draft(
        now=datetime(2026, 10, 25, tzinfo=timezone.utc))['economic_policy']
    policy = draft['economic_policy']
    for block in blocks:
        block.update(trade_count=30, uncertainty_method=policy['uncertainty_method'],
                     uncertainty_parameters=policy['uncertainty_parameters'])
    assert evaluate_economic_validation_draft(draft, blocks)['economic_evaluation'] == 'INSUFFICIENT_DATA'
    full = dict(method=policy['uncertainty_method'], parameters=policy['uncertainty_parameters'],
        observed_days=126, cash_excess_lower_bound='0.001', pool_excess_lower_bound='0.001')
    assert evaluate_economic_validation_draft(draft, blocks, window_uncertainty=full)['economic_evaluation'] == 'PASS'
    full['pool_excess_lower_bound'] = '-0.001'
    assert evaluate_economic_validation_draft(draft, blocks, window_uncertainty=full)['economic_evaluation'] == 'FAIL'


@pytest.mark.parametrize('key,value', [('strategy_net_return', '0.04'),
    ('maximum_drawdown', '0.21'), ('excess_lower_bound', '-0.01')])
def test_explicit_economic_failures_are_not_hidden_by_other_passing_blocks(key, value):
    draft, blocks = fixture()
    blocks[0][key] = value
    if key == 'strategy_net_return':
        blocks[0]['cost_returns']['1'] = value
    assert evaluate_economic_validation_draft(draft, blocks)['economic_evaluation'] == 'FAIL'


@pytest.mark.parametrize('key,value', [('trade_count', 0),
    ('uncertainty_method', 'DIFFERENT'), ('scope', 'ISOLATED_SECURITY_RETROSPECTIVE'),
    ('cost_returns', None)])
def test_insufficient_or_incomparable_results_cannot_pass(key, value):
    draft, blocks = fixture()
    blocks[0][key] = value
    assert evaluate_economic_validation_draft(draft, blocks)['economic_evaluation'] == 'INSUFFICIENT_DATA'


@pytest.mark.parametrize('fault', ['nan', 'boolean', 'overlap', 'missing_session', 'wrong_horizon',
    'between_block_gap', 'loss_without_drawdown'])
def test_invalid_inputs_fail_closed(fault):
    draft, blocks = fixture()
    if fault == 'nan':
        blocks[0]['strategy_net_return'] = 'NaN'
    elif fault == 'boolean':
        blocks[0]['pool_net_return'] = True
    elif fault == 'overlap':
        blocks[1]['sessions'] = blocks[0]['sessions']
    elif fault == 'missing_session':
        blocks[0]['sessions'].pop()
    elif fault == 'between_block_gap':
        sessions = [day for block in blocks for day in block['sessions']]
        sessions.pop(42)
        sessions.append(next_exchange_session('SSE', date.fromisoformat(sessions[-1])).isoformat())
        for i, block in enumerate(blocks):
            block['sessions'] = sessions[i * 42:(i + 1) * 42]
    elif fault == 'loss_without_drawdown':
        blocks[0].update(strategy_net_return='-0.5', cash_net_return='-0.8',
                         pool_net_return='-0.7', maximum_drawdown='0')
        blocks[0]['cost_returns']['1'] = '-0.5'
    else:
        draft['block_sessions'] = 41
    with pytest.raises(ValueError):
        evaluate_economic_validation_draft(draft, blocks)


@pytest.mark.parametrize('drift', [False, True])
def test_bound_application_retains_failures_and_rejects_draft_drift(tmp_path, monkeypatch, drift):
    from value_investment_agent.application.hotspot.quantitative_validation import (
        diagnose_retained_economic_draft, ProtocolBinding)
    from value_investment_agent.application.hotspot import independent_validation

    now = datetime(2026, 10, 25, tzinfo=timezone.utc)
    path = tmp_path / 'draft.json'
    path.write_text(json.dumps(build_economic_validation_draft(now=now)), encoding='utf-8')
    binding = ProtocolBinding(path='draft.json', sha256=sha256(path.read_bytes()).hexdigest())

    def fixture_evidence(root, cutoff):
        if drift:
            path.write_bytes(path.read_bytes() + b' ')
        return dict(protocol={'registered_before_validation': False},
            decision_availability={'source_acquired_after_decision': 1},
            replay_content_sha256='a' * 64, summary={'strict_closed_trade_count': 0},
            costed_partitions=[], strict_rejection_counts={'MISSING_DATED_STOCK_STATUS': 1},
            source_bindings=[])

    monkeypatch.setattr(independent_validation, '_execution_evidence', fixture_evidence)
    if drift:
        with pytest.raises(ValueError, match='hash mismatch'):
            diagnose_retained_economic_draft(root=tmp_path, binding=binding, now=now)
    else:
        result = diagnose_retained_economic_draft(root=tmp_path, binding=binding, now=now)
        assert result['economic_evaluation'] == 'INSUFFICIENT_DATA'
        checks = {row['check']: row['status'] for row in result['checks']}
        assert checks['HISTORICAL_SOURCE_PIT'] == checks['PREDECLARED_UNTOUCHED_OOS'] == 'FAIL'
        assert result['formal_eligibility'] is False
