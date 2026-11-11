"""TEST_ONLY operating research arithmetic, not real-source or economic approval."""
from copy import deepcopy
from decimal import Decimal as D, localcontext
import json

import pytest

from value_investment_agent.domain.valuation.industrial_earnings_paths import build_industrial_earnings_paths
from value_investment_agent.domain.valuation.signed_parent_profit import build_signed_parent_profit_path


@pytest.fixture
def inputs():
    history = dict(operating_revenue='1000', cost_of_sales='600', taxes_surcharges='10',
        selling='150', administration='30', research='10', profit_before_tax='180',
        asset_impairment='-20', income_tax='40', minority_profit='-10', parent_profit='150')
    row = dict(year=1, revenue_growth='.10', commercial_margin='.11', inventory_impairment_ratio='.02',
        goodwill_impairment_cny='15', other_asset_impairment_cny='3', other_pbt_cny='10',
        tax_research_rate='.25', signed_nci_cny='-5')
    return dict(historical_ttm=history, scenarios={name: [dict(row, year=year) for year in range(1, 6)]
                                                for name in ('bear', 'base', 'bull')})


def test_hand_bridge_compounding_history_residual_and_parent_function(inputs):
    before = deepcopy(inputs)
    result = build_industrial_earnings_paths(**inputs)
    assert result['status'] == 'CONDITIONAL_EARNINGS_RESEARCH_NOT_APPROVED'
    h = result['historical_reference']
    assert D(h['commercial_cost_ratio']) == D('.8')
    assert D(h['commercial_subtotal_cny']) == 200 and D(h['other_pbt_cny']) == 0
    first = result['scenarios']['base']['rows'][0]
    # revenue1100, commercial121, inventory22, other+10/-3 => pre-goodwill106;
    # PBT91, tax26.5 WITHOUT goodwill shield, NCI-5 => parent69.5.
    expected = dict(revenue_cny='1100', commercial_subtotal_cny='121', inventory_impairment_cny='22',
        pre_goodwill_pbt_cny='106', group_pbt_cny='91', income_tax_cny='26.5',
        signed_nci_cny='-5', parent_profit_cny='69.5')
    for key, value in expected.items(): assert D(first[key]) == D(value)
    assert D(first['commercial_cost_ratio_delta']) == D('.09')
    assert all(D(row['bridge_residual_cny']) == D(row['operating_bridge_residual_cny']) == 0
        for row in result['scenarios']['base']['rows'])
    with localcontext() as ctx:
        ctx.prec = 48
        assert D(result['scenarios']['base']['rows'][-1]['revenue_cny']) == D(1000)*D('1.1')**5
    rows = result['scenarios']['base']['rows']
    parent = build_signed_parent_profit_path(years=[1, 2, 3, 4, 5],
        group_pbt_cny=[r['group_pbt_cny'] for r in rows],
        tax_assumptions=[dict(basis='amount_cny', value=r['income_tax_cny']) for r in rows],
        signed_nci_cny=[r['signed_nci_cny'] for r in rows], currency='CNY')
    assert [r['parent_profit_cny'] for r in parent['rows']] == [r['parent_profit_cny'] for r in rows]
    assert inputs == before and json.loads(json.dumps(result, allow_nan=False)) == result
    assert result['normalized_parent_profit_cny'] is None and not result['economic_approval']
    assert result['action'] == 'no_order' and 'scenario_inputs' not in result and 'valuation' not in result


def test_goodwill_loss_no_tax_shield_and_no_historical_impairment_addback(inputs):
    original = build_industrial_earnings_paths(**inputs)
    for row in inputs['scenarios']['base']: row['goodwill_impairment_cny'] = '25'
    changed = build_industrial_earnings_paths(**inputs)
    for old, new in zip(original['scenarios']['base']['rows'], changed['scenarios']['base']['rows']):
        assert old['income_tax_cny'] == new['income_tax_cny']
        assert D(old['parent_profit_cny'])-D(new['parent_profit_cny']) == 10
    inputs['historical_ttm']['asset_impairment'] = '-200'
    history_changed = build_industrial_earnings_paths(**inputs)
    for name in ('bear', 'base', 'bull'):
        for old, new in zip(changed['scenarios'][name]['rows'], history_changed['scenarios'][name]['rows']):
            assert {k: v for k, v in old.items() if k != 'change_from_historical_parent'} == {
                k: v for k, v in new.items() if k != 'change_from_historical_parent'}
    assert D(history_changed['historical_reference']['other_pbt_cny']) == 180


def test_negative_margin_losses_zero_tax_and_no_required_nci_convergence(inputs):
    for row in inputs['scenarios']['bear']:
        row.update(commercial_margin='-.1', signed_nci_cny='-100')
    result = build_industrial_earnings_paths(**inputs)
    for row in result['scenarios']['bear']['rows']:
        assert D(row['commercial_cost_ratio']) > 1 and D(row['income_tax_cny']) == 0
        assert D(row['group_pbt_cny']) < 0 and D(row['signed_nci_cny']) == -100
    inputs['historical_ttm'].update(operating_revenue='0')
    result = build_industrial_earnings_paths(**inputs)
    assert result['historical_reference']['commercial_cost_ratio'] is None
    row = result['scenarios']['base']['rows'][0]
    assert D(row['revenue_cny']) == 0 and row['commercial_cost_ratio_delta'] is None


def test_labels_not_resorted_and_all_hypotheses_retained(inputs):
    for row in inputs['scenarios']['bear']: row['commercial_margin'] = '.3'
    for row in inputs['scenarios']['bull']: row['commercial_margin'] = '.01'
    result = build_industrial_earnings_paths(**inputs)
    assert D(result['scenarios']['bear']['rows'][0]['parent_profit_cny']) > D(result['scenarios']['bull']['rows'][0]['parent_profit_cny'])
    for name in ('bear', 'base', 'bull'):
        for row, hypothesis in zip(result['scenarios'][name]['rows'], inputs['scenarios'][name]):
            assert row['inputs']['year'] == hypothesis['year']
            assert all(D(row['inputs'][key]) == D(value) for key, value in hypothesis.items() if key != 'year')


def test_goodwill_can_make_pbt_negative_without_a_tax_benefit(inputs):
    for row in inputs['scenarios']['base']:
        row.update(goodwill_impairment_cny='200', signed_nci_cny='0')
    first = build_industrial_earnings_paths(**inputs)['scenarios']['base']['rows'][0]
    assert D(first['pre_goodwill_pbt_cny']) == 106
    assert D(first['group_pbt_cny']) == -94
    assert D(first['income_tax_cny']) == D('26.5')
    assert D(first['parent_profit_cny']) == D('-120.5')


@pytest.mark.parametrize('fault', ['missing_history', 'history_identity', 'negative_cost', 'negative_revenue',
    'float_history', 'nonfinite_history', 'unknown_nonnumeric_history', 'missing_scenario', 'extra_scenario',
    'short_path', 'year_bool', 'year_order', 'year_string', 'missing_field', 'extra_field', 'old_delta',
    'growth', 'margin', 'negative_inventory', 'negative_goodwill', 'negative_other_loss', 'rate_high',
    'rate_negative', 'bool', 'float', 'nan', 'infinity', 'null'])
def test_strict_contracts_and_no_unknown_zero(inputs, fault):
    h, scenarios = inputs['historical_ttm'], inputs['scenarios']
    row = scenarios['base'][0]
    if fault == 'missing_history': del h['minority_profit']
    elif fault == 'history_identity': h['parent_profit'] = '151'
    elif fault == 'negative_cost': h['research'] = '-1'
    elif fault == 'negative_revenue': h['operating_revenue'] = '-1'
    elif fault == 'float_history': h['income_tax'] = 40.0
    elif fault == 'nonfinite_history': h['income_tax'] = 'NaN'
    elif fault == 'unknown_nonnumeric_history': h['metadata'] = {'unit': 'CNY'}
    elif fault == 'missing_scenario': del scenarios['bull']
    elif fault == 'extra_scenario': scenarios['fourth'] = scenarios['bear']
    elif fault == 'short_path': scenarios['base'].pop()
    elif fault == 'year_bool': row['year'] = True
    elif fault == 'year_order': row['year'] = 2
    elif fault == 'year_string': row['year'] = '1'
    elif fault == 'missing_field': del row['signed_nci_cny']
    elif fault == 'extra_field': row['fake'] = '0'
    elif fault == 'old_delta': row['commercial_cost_ratio_delta'] = row.pop('commercial_margin')
    elif fault == 'growth': row['revenue_growth'] = '-1'
    elif fault == 'margin': row['commercial_margin'] = '1.01'
    elif fault == 'negative_inventory': row['inventory_impairment_ratio'] = '-.01'
    elif fault == 'negative_goodwill': row['goodwill_impairment_cny'] = '-1'
    elif fault == 'negative_other_loss': row['other_asset_impairment_cny'] = '-1'
    elif fault == 'rate_high': row['tax_research_rate'] = '1.01'
    elif fault == 'rate_negative': row['tax_research_rate'] = '-.01'
    else: row['signed_nci_cny'] = {'bool': False, 'float': -5.0, 'nan': 'NaN', 'infinity': 'Infinity', 'null': None}[fault]
    with pytest.raises(ValueError): build_industrial_earnings_paths(**inputs)


def test_precision_isolated_and_explicit_zero_losses(inputs):
    for row in inputs['scenarios']['base']:
        row.update(inventory_impairment_ratio='0', goodwill_impairment_cny='0', other_asset_impairment_cny='0')
    baseline = build_industrial_earnings_paths(**inputs)
    with localcontext() as ctx:
        ctx.prec = 6
        assert build_industrial_earnings_paths(**inputs) == baseline
    row = baseline['scenarios']['base']['rows'][0]
    assert all(D(row[key]) == 0 for key in ('inventory_impairment_cny', 'goodwill_impairment_cny', 'other_asset_impairment_cny'))


def test_reported_parent_change_five_contributions_sum_for_all_scenarios_years(inputs):
    result = build_industrial_earnings_paths(**inputs)
    fields = ('commercial_subtotal_change_cny', 'asset_impairment_change_cny', 'other_pbt_change_cny',
              'income_tax_change_cny', 'signed_nci_change_cny')
    for scenario in result['scenarios'].values():
        for row in scenario['rows']:
            bridge = row['change_from_historical_parent']
            assert sum(D(bridge[key]) for key in fields) == D(bridge['parent_profit_change_cny'])
            assert D(bridge['residual_cny']) == 0
            assert D(bridge['parent_profit_change_cny']) == D(row['parent_profit_cny'])-150
    first = result['scenarios']['base']['rows'][0]['change_from_historical_parent']
    assert [D(first[key]) for key in fields] == [D('-79'), D('-20'), D('10'), D('13.5'), D('-5')]
    assert result['parent_change_comparison_scope'] == 'HISTORICAL_REPORTED_PARENT_NOT_EX_NONRECURRING_OR_NORMALIZED'


def test_loss_nonrecurrence_and_negative_nci_reversal_not_commercial_improvement(inputs):
    for row in inputs['scenarios']['base']:
        row.update(revenue_growth='0', commercial_margin='.2', inventory_impairment_ratio='0',
            goodwill_impairment_cny='0', other_asset_impairment_cny='0', other_pbt_cny='0',
            tax_research_rate='.2', signed_nci_cny='0')
    rows = build_industrial_earnings_paths(**inputs)['scenarios']['base']['rows']
    for row in rows:
        bridge = row['change_from_historical_parent']
        assert D(row['parent_profit_cny']) == 160
        assert D(bridge['commercial_subtotal_change_cny']) == 0
        assert D(bridge['asset_impairment_change_cny']) == 20
        assert D(bridge['signed_nci_change_cny']) == -10
        assert D(bridge['parent_profit_change_cny']) == 10
        assert D(bridge['residual_cny']) == 0
