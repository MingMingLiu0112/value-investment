"""Synthetic period contracts only; no company fixture or source admission."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from value_investment_agent.domain.research import period_earnings_assembly_v1 as mod

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def segment(start, end, pbt, tax, nci, *, kind='REPORTED_FACT', ref='TEST_ONLY:source'):
    return dict(period_start=start, period_end=end, kind=kind, currency='CNY', scope='consolidated',
        group_pbt_cny=pbt, income_tax_cny=tax, signed_nci_cny=nci,
        source_refs=[ref] if kind != 'FORECAST_ASSUMPTION' else [],
        assumption_refs=[ref] if kind == 'FORECAST_ASSUMPTION' else [])


@pytest.fixture
def actuals():
    return (segment('2026-01-01', '2026-09-30', '90', '18', '-3', ref='TEST_ONLY:9m'),
            segment('2026-01-01', '2026-06-30', '100', '20', '-1', ref='TEST_ONLY:h1'))


def rolling_segments(actuals):
    return [mod.subtract_same_year_ytd(*actuals, asof=NOW),
            segment('2026-10-01', '2026-12-31', '30', '6', '1', kind='FORECAST_ASSUMPTION', ref='TEST_ONLY:q4'),
            segment('2027-01-01', '2027-06-30', '70', '14', '2', kind='FORECAST_ASSUMPTION', ref='TEST_ONLY:h1future')]


def assemble(rows, **changes):
    args = dict(year=1, period_start='2026-07-01', period_end='2027-06-30', segments=rows, asof=NOW)
    args.update(changes)
    return mod.assemble_annual_earnings(**args)


def test_actual_ytd_difference_keeps_negative_amounts_and_provenance(actuals):
    before = deepcopy(actuals)
    actuals[0]['parent_profit_cny'] = '75'
    actuals[1]['parent_profit_cny'] = '81'
    result = mod.subtract_same_year_ytd(*actuals, asof=NOW)
    assert result['period_start'] == '2026-07-01' and result['period_end'] == '2026-09-30'
    assert result['kind'] == 'DERIVED_FACT'
    assert [result[k] for k in mod.AMOUNTS] == ['-10', '-2', '-2']
    assert result['parent_profit_cny'] == '-6'
    assert result['source_refs'] == ['TEST_ONLY:9m', 'TEST_ONLY:h1']
    assert result['derivation']['operands'] == list(actuals)
    for current, original in zip(actuals, before):
        assert {k: v for k, v in current.items() if k != 'parent_profit_cny'} == original


def test_rolling_actual_and_forecast_assembly_calls_shared_parent_helper(actuals, monkeypatch):
    rows = rolling_segments(actuals)
    before = deepcopy(rows)
    calls = []
    original = mod.build_signed_parent_profit_path
    def traced(**kwargs):
        calls.append(deepcopy(kwargs))
        return original(**kwargs)
    monkeypatch.setattr(mod, 'build_signed_parent_profit_path', traced)
    result = assemble(rows)
    assert result['annual_row'] == dict(year=1, period_start='2026-07-01', period_end='2027-06-30',
        period_basis='ROLLING_FULL_YEAR', scope='consolidated', currency='CNY', group_pbt_cny='90',
        tax_assumption=dict(basis='amount_cny', value='18'), signed_nci_cny='1')
    assert result['parent_bridge']['parent_profit_cny'] == '71'
    assert result['parent_bridge']['bridge_residual_cny'] == '0'
    assert len(calls) == 4 and calls[-1]['group_pbt_cny'] == [Decimal('90')]
    assert result['source_refs'] == ['TEST_ONLY:9m', 'TEST_ONLY:h1']
    assert result['assumption_refs'] == ['TEST_ONLY:q4', 'TEST_ONLY:h1future']
    assert result['contains_forecast_assumptions'] and not result['main_range_adopted']
    assert not result['formal_eligibility'] and result['action'] == 'no_order'
    assert rows == before


@pytest.mark.parametrize('damage', ['gap', 'overlap', 'reorder', 'missing_h1', 'half_year_model',
    'outside_end', 'wrong_scope', 'wrong_currency', 'missing_pbt', 'nan', 'float',
    'missing_refs', 'future_source', 'naive_time', 'future_asof', 'parent_mismatch'])
def test_incomplete_or_invalid_assembly_rejected(actuals, damage):
    rows = rolling_segments(actuals)
    options = {}
    if damage == 'gap': rows[1]['period_start'] = '2026-10-02'
    elif damage == 'overlap': rows[1]['period_start'] = '2026-09-30'
    elif damage == 'reorder': rows.reverse()
    elif damage == 'missing_h1': rows.pop()
    elif damage == 'half_year_model': options['period_end'] = '2026-12-31'
    elif damage == 'outside_end': rows[2]['period_end'] = '2027-12-31'
    elif damage == 'wrong_scope': rows[1]['scope'] = 'parent'
    elif damage == 'wrong_currency': rows[1]['currency'] = 'USD'
    elif damage == 'missing_pbt': del rows[1]['group_pbt_cny']
    elif damage == 'nan': rows[1]['income_tax_cny'] = 'NaN'
    elif damage == 'float': rows[1]['group_pbt_cny'] = 30.0
    elif damage == 'missing_refs': rows[1]['assumption_refs'] = []
    elif damage == 'future_source': rows[1]['available_at'] = '2027-01-01T00:00:00+00:00'
    elif damage == 'naive_time': rows[1]['available_at'] = '2026-10-01T00:00:00'
    elif damage == 'future_asof': rows[1]['asof'] = '2027-01-01T00:00:00+00:00'
    else: rows[1]['parent_profit_cny'] = '999'
    with pytest.raises(ValueError): assemble(rows, **options)


@pytest.mark.parametrize('damage', ['year', 'not9m', 'notH1', 'scope', 'currency', 'forecast', 'parent_only', 'future'])
def test_ytd_requires_same_year_actual_group_inputs(actuals, damage):
    nine, half = actuals
    if damage == 'year': half.update(period_start='2025-01-01', period_end='2025-06-30')
    elif damage == 'not9m': nine['period_end'] = '2026-12-31'
    elif damage == 'notH1': half['period_end'] = '2026-03-31'
    elif damage == 'scope': half['scope'] = 'consolidated_parent'
    elif damage == 'currency': half['currency'] = 'CNY_million'
    elif damage == 'forecast': half.update(kind='FORECAST_ASSUMPTION', assumption_refs=['TEST_ONLY'])
    elif damage == 'parent_only': half['parent_profit_cny'] = half.pop('group_pbt_cny')
    else: nine['available_at'] = '2026-11-02T00:00:00+00:00'
    with pytest.raises(ValueError): mod.subtract_same_year_ytd(nine, half, asof=NOW)


def test_9m_is_not_full_year(actuals):
    with pytest.raises(ValueError, match='INCOMPLETE_MODEL_YEAR_COVERAGE'):
        mod.assemble_annual_earnings(year=1, period_start='2026-01-01', period_end='2026-12-31',
                                    segments=[actuals[0]], asof=NOW)


def test_complete_leap_year_and_ten_model_year_rows():
    rows = []
    for step in range(1, 11):
        year = 2027 + step
        first, last = f'{year}-01-01', f'{year}-12-31'
        parts = [segment(first, f'{year}-06-30', '10.01', '1.01', '-0.01', kind='FORECAST_ASSUMPTION'),
                 segment(f'{year}-07-01', last, '20.02', '2.02', '0.02', kind='FORECAST_ASSUMPTION')]
        result = mod.assemble_annual_earnings(year=step, period_start=first, period_end=last, segments=parts)
        rows.append(result['annual_row'])
        assert result['parent_bridge']['parent_profit_cny'] == '26.99'
    assert [r['year'] for r in rows] == list(range(1, 11))
    assert all(r['period_basis'] == 'FY' for r in rows)


def test_availability_cutoff_required_and_preserved(actuals):
    for row in actuals: row['available_at'] = '2026-10-31T00:00:00+00:00'
    with pytest.raises(ValueError, match='ASOF_REQUIRED'):
        mod.subtract_same_year_ytd(*actuals)
    result = mod.subtract_same_year_ytd(*actuals, asof=NOW)
    assert result['available_at'] == '2026-10-31T00:00:00+00:00'
    assert result['asof'] == NOW.isoformat()


@pytest.fixture
def point_inputs():
    rows = [dict(field=field, value=value, period_start='2025-10-01', period_end='2025-12-31',
        kind='DERIVED_FACT', currency='CNY', scope='consolidated',
        source_refs=['TEST_ONLY:FY2025', 'TEST_ONLY:9M2025'], assumption_refs=[],
        derivation=dict(formula='FY_MINUS_9M')) for field, value in (
            ('revenue', '100'), ('cost', '70'), ('surcharges', '5'), ('selling', '15'),
            ('admin', '5'), ('research', '4'), ('pre_tax_profit', '1'))]
    drivers = dict(volume_change='0', realization_mix_change='0', unit_cost_change='0.1',
        fixed_cogs_share='0.5', opex_change='0', surcharge_ratio='0.05', other_pretax_cny='0',
        source_refs=['TEST_ONLY:FY2025'], assumption_refs=['TEST_ONLY:explicit_point'])
    target = dict(period_start='2026-10-01', period_end='2026-12-31', asof=NOW)
    return rows, drivers, target


def test_q4_point_preserves_low_base_negative_projected_profit(point_inputs):
    original = deepcopy(point_inputs)
    result = mod.project_operating_period(*point_inputs)
    assert result['period_basis'] == 'Q4' and result['kind'] == 'FORECAST_ASSUMPTION'
    assert Decimal(result['group_pbt_cny']) == Decimal('-6')
    assert {k: Decimal(v) for k, v in result['components'].items()} == dict(
        revenue_cny=Decimal(100), cogs_cny=Decimal(77), opex_cny=Decimal(24),
        surcharges_cny=Decimal(5), other_pretax_cny=Decimal(0))
    assert result['income_tax_cny'] is result['signed_nci_cny'] is None
    assert result['source_refs'] == ['TEST_ONLY:FY2025', 'TEST_ONLY:9M2025']
    assert result['assumption_refs'] == ['TEST_ONLY:explicit_point']
    assert point_inputs == original and not result['main_range_adopted']


@pytest.mark.parametrize('start,end,kind', [('01-01', '03-31', 'Q1'), ('04-01', '06-30', 'Q2'),
    ('07-01', '09-30', 'Q3'), ('10-01', '12-31', 'Q4'), ('01-01', '06-30', 'H1'), ('01-01', '12-31', 'FY')])
def test_same_period_next_year_point_projection(point_inputs, start, end, kind):
    rows, drivers, target = point_inputs
    for row in rows: row.update(period_start='2024-'+start, period_end='2024-'+end)
    target.update(period_start='2025-'+start, period_end='2025-'+end)
    assert mod.project_operating_period(rows, drivers, target)['period_basis'] == kind


@pytest.mark.parametrize('damage', ['quarter_as_fy', 'half_as_quarter', 'skip_year', 'same_year',
    'duplicate', 'missing', 'mixed_period', 'parent', 'unit', 'forecast_baseline', 'negative_cost',
    'fixed_share', 'surcharge', 'negative_revenue', 'negative_opex', 'missing_driver', 'range_not_point',
    'missing_assumptions', 'future_source'])
def test_point_invalid_period_or_economic_contract_rejected(point_inputs, damage):
    rows, drivers, target = point_inputs
    if damage == 'quarter_as_fy': target['period_start'] = '2026-01-01'
    elif damage == 'half_as_quarter':
        for row in rows: row.update(period_start='2025-01-01', period_end='2025-06-30')
        target.update(period_start='2026-04-01', period_end='2026-06-30')
    elif damage == 'skip_year': target.update(period_start='2027-10-01', period_end='2027-12-31')
    elif damage == 'same_year': target.update(period_start='2025-10-01', period_end='2025-12-31')
    elif damage == 'duplicate': rows[-1]['field'] = 'cost'
    elif damage == 'missing': rows.pop()
    elif damage == 'mixed_period': rows[0]['period_start'] = '2025-01-01'
    elif damage == 'parent': rows[0]['scope'] = 'parent'
    elif damage == 'unit': rows[0]['currency'] = 'CNY_million'
    elif damage == 'forecast_baseline': rows[0]['kind'] = 'FORECAST_ASSUMPTION'
    elif damage == 'negative_cost': rows[1]['value'] = '-1'
    elif damage == 'fixed_share': drivers['fixed_cogs_share'] = '1.01'
    elif damage == 'surcharge': drivers['surcharge_ratio'] = '-0.01'
    elif damage == 'negative_revenue': drivers['volume_change'] = '-1.1'
    elif damage == 'negative_opex': drivers['opex_change'] = '-1.1'
    elif damage == 'missing_driver': del drivers['other_pretax_cny']
    elif damage == 'range_not_point': drivers['volume_change'] = {'lower': '0', 'upper': '0.1'}
    elif damage == 'missing_assumptions': drivers['assumption_refs'] = []
    else: rows[0]['available_at'] = '2026-11-02T00:00:00+00:00'
    with pytest.raises(ValueError): mod.project_operating_period(rows, drivers, target)


def test_zero_revenue_and_signed_other_remain_explicit(point_inputs):
    rows, drivers, target = point_inputs
    drivers.update(volume_change='-1', other_pretax_cny='-2')
    result = mod.project_operating_period(rows, drivers, target)
    assert Decimal(result['components']['revenue_cny']) == 0
    assert Decimal(result['group_pbt_cny']) < 0
    assert result['components']['other_pretax_cny'] == '-2'
