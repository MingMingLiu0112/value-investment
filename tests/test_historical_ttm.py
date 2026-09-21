from copy import deepcopy

import pytest

from value_investment_agent.historical_ttm import trailing_profit


def points():
    rows = []
    for period, value in [('2025-09-30', '37883383'),
                          ('2024-12-31', '38537237'), ('2024-09-30', '31699114')]:
        rows.append(dict(symbol='000333', field_name='parent_attributable_net_income',
                         period_label=period, value=value, unit='CNY thousand',
                         validation_status='verified', source_id=period,
                         raw_file_hash='a' * 64, timestamp_precision='timestamp',
                         availability_verified=True, published_at='2025-10-30T20:00:00+08:00',
                         available_at='2025-10-30T20:00:00+08:00',
                         metadata=dict(period_start=period[:4] + '-01-01',
                                       scope='consolidated_parent_attributable',
                                       accounting_basis='China GAAP',
                                       ttm_comparability_verified=True,
                                       comparability_evidence_id='synthetic-review')))
    return rows


def calculate(rows, decision='2025-10-31T09:30:00+08:00'):
    return trailing_profit(rows, symbol='000333', period_end='2025-09-30',
                           decision_at=decision)


def test_arithmetic_preserves_all_evidence_without_approving_backtest():
    rows = points()
    original = deepcopy(rows)
    result = calculate(rows)
    assert result['value'] == 44721506
    assert len(result['evidence']) == 3
    assert result['backtest_ready'] is False
    assert rows == original


def test_no_future_financials():
    with pytest.raises(ValueError, match='Missing verified'):
        calculate(points(), '2025-10-30T15:00:00+08:00')


@pytest.mark.parametrize('key,value', [
    ('period_start', '2025-07-01'), ('scope', 'parent_only'),
    ('ttm_comparability_verified', False), ('comparability_evidence_id', ''),
])
def test_rejects_unverified_or_non_cumulative_inputs(key, value):
    rows = points()
    rows[0]['metadata'][key] = value
    with pytest.raises(ValueError):
        calculate(rows)


@pytest.mark.parametrize('change', ['unit', 'basis', 'review'])
def test_rejects_mixed_basis(change):
    rows = points()
    if change == 'unit':
        rows[1]['unit'] = 'CNY'
    elif change == 'basis':
        rows[1]['metadata']['accounting_basis'] = 'IFRS'
    else:
        rows[1]['metadata']['comparability_evidence_id'] = 'different-review'
    with pytest.raises(ValueError, match='Incompatible'):
        calculate(rows)


def test_unapproved_candidate_cannot_be_used():
    rows = points()
    rows[0]['validation_status'] = 'candidate'
    with pytest.raises(ValueError, match='Missing verified'):
        calculate(rows)
