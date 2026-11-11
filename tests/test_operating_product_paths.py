"""TEST_ONLY product hypotheses; native arithmetic success is not source approval."""
from copy import deepcopy
from decimal import Decimal as D, localcontext
import json

import pytest

from test_source_native_candidate_v2 import test_only_ledger as make_ledger
from value_investment_agent.domain.valuation.operating_product_paths import build_product_operating_paths
from value_investment_agent.domain.valuation.source_native_cash_v1 import replay_timing_delay_inputs


@pytest.fixture
def inputs():
    annual = dict(operating_revenue=['1000', '1000'], cost_of_sales=['200', '200'],
        taxes_surcharges=['50', '50'], selling=['50', '50'], administration=['50', '50'],
        research=['10', '10'], profit_before_tax=['400', '400'], income_tax=['100', '100'],
        parent_profit=['280', '280'], ex_parent_profit=['270', '270'])
    interim = dict(operating_revenue=['500', '500'], cost_of_sales=['120', '100'],
        taxes_surcharges=['25', '25'], selling=['25', '25'], administration=['25', '25'],
        research=['5', '5'], profit_before_tax=['190', '200'], income_tax=['50', '50'],
        parent_profit=['130', '140'], ex_parent_profit=['125', '135'])
    row = dict(moutai_volume_growth='0', moutai_realization_growth='0',
        series_volume_growth='0', series_realization_growth='0', other_revenue_growth='0', cost_ratio='.22')
    return dict(annual=annual, interim=interim,
        product_revenue_cny=dict(moutai='350', series='100', other='50'),
        policy={name: [dict(row) for _ in range(5)] for name in ('bear', 'base', 'bull')},
        ledger=make_ledger(D('1000'), '2026-06-30'), opening_book='1000')


def test_reference_allocation_full_group_hand_profit_bridge_and_native_replay(inputs):
    before = deepcopy(inputs)
    result = build_product_operating_paths(**inputs)
    assert result['status'] == 'CASH_CONTRACT_REPLAYED_NOT_ECONOMIC_APPROVAL'
    assert inputs == before
    allocation = result['reference_allocation']
    assert allocation['scope'] == 'RESEARCH_REFERENCE_ALLOCATION_NOT_OBSERVED_TTM_PRODUCT_REVENUE'
    assert {key: D(row['ttm_reference_revenue_cny']) for key, row in allocation['products'].items()} == {
        'moutai': D('700'), 'series': D('200'), 'other': D('100')}
    assert sum(D(row['ttm_reference_revenue_cny']) for row in allocation['products'].values()) == D('1000')
    row = result['operating_rows']['base'][0]
    # TTM PBT=390, tax=100, parent=270, ex-parent=260. Selected subtotal=620,
    # so other pretax=-230. Flat policy must reconstruct 260 exactly (up to Decimal roundoff).
    assert D(row['revenue']) == 1000 and D(row['cost']) == 220
    assert D(row['legacy_pre_tax_profit']) == 390
    assert D(row['other_pre_tax_balance']) == -230
    assert D(row['net_parent_nonrecurring_difference']) == 10
    assert abs(D(row['legacy_ex_parent'])-260) < D('1e-40')
    assert result['scenario_inputs'] == replay_timing_delay_inputs(
        plan=inputs['ledger']['plan'], history=inputs['ledger']['history'],
        opening_book=inputs['opening_book'], scenarios=result['scenarios'])
    for name in ('bear', 'base', 'bull'):
        cash = result['scenarios'][name]['annual_rows']
        assert len(cash) == 5 and D(cash[1]['released']) == D(cash[0]['newly_withheld'])
        assert all(D(row['cash_close']) >= D(result['scenarios'][name]['cash_floor']) for row in cash)
        assert D(cash[-1]['delayed_close']) == 0
        assert D(result['scenarios'][name]['terminal_growth']) == 0
    assert result['normalized_parent_profit_cny'] is None and result['economic_approval'] is False
    assert result['action'] == 'no_order'
    assert json.loads(json.dumps(result, allow_nan=False)) == result


def test_product_volume_and_realization_compound_separately_not_whole_group(inputs):
    for row in inputs['policy']['bull']:
        row.update(moutai_volume_growth='.10', moutai_realization_growth='.20',
            series_volume_growth='-.05', series_realization_growth='.04', other_revenue_growth='.03')
    result = build_product_operating_paths(**inputs)
    assert result['status'] == 'CASH_CONTRACT_REPLAYED_NOT_ECONOMIC_APPROVAL'
    with localcontext() as ctx:
        ctx.prec = 48
        for year, row in enumerate(result['operating_rows']['bull'], 1):
            expected = dict(moutai=D(700)*D('1.1')**year*D('1.2')**year,
                series=D(200)*D('.95')**year*D('1.04')**year, other=D(100)*D('1.03')**year)
            for product, value in expected.items():
                assert abs(D(row['product_revenue_cny'][product])-value) < D('1e-38')
            assert abs(D(row['revenue'])-sum(expected.values())) < D('1e-38')
            assert D(row['revenue']) != D(1000)*(D('1.1')*D('1.2'))**year
        first = result['operating_rows']['bull'][0]
        rev = D(700)*D('1.1')*D('1.2')+D(200)*D('.95')*D('1.04')+D(100)*D('1.03')
        pretax = rev*(1-D('.22')-D('.16'))-D(230)
        parent = pretax*(1-D(100)/390)*(D(270)/290)
        assert abs(D(first['legacy_ex_parent'])-(parent-10)) < D('1e-40')
    assert result['operating_rows']['base'][0]['drivers']['moutai_volume_growth'] == '0'


def test_other_revenue_not_scaled_by_wine_and_zero_other_is_explicit(inputs):
    for row in inputs['policy']['bear']:
        row['other_revenue_growth'] = '.1'
    result = build_product_operating_paths(**inputs)
    first = result['operating_rows']['bear'][0]['product_revenue_cny']
    assert D(first['moutai']) == 700 and D(first['series']) == 200 and D(first['other']) == 110
    inputs['product_revenue_cny'].update(series='150', other='0')
    result = build_product_operating_paths(**inputs)
    assert D(result['reference_allocation']['products']['other']['ttm_reference_revenue_cny']) == 0


@pytest.mark.parametrize('fault', ['wine_only', 'negative_product', 'missing_product', 'extra_product',
    'missing_field', 'extra_field', 'short_pair', 'missing_scenario', 'short_horizon',
    'extra_driver', 'missing_driver', 'float', 'bool', 'nan', 'infinity', 'minus_one', 'cost',
    'history_float', 'plan_bool', 'retention', 'held', 'floor', 'budget', 'fund', 'scope', 'two_annual',
    'blocked', 'branch', 'terminal'])
def test_malformed_contracts_rejected(inputs, fault):
    if fault == 'wine_only': inputs['product_revenue_cny']['other'] = '0'
    elif fault == 'negative_product': inputs['product_revenue_cny'].update(moutai='-1', series='451')
    elif fault == 'missing_product': del inputs['product_revenue_cny']['other']
    elif fault == 'extra_product': inputs['product_revenue_cny']['fake'] = '0'
    elif fault == 'missing_field': del inputs['annual']['income_tax']
    elif fault == 'extra_field': inputs['annual']['fake'] = ['0', '0']
    elif fault == 'short_pair': inputs['interim']['income_tax'] = ['50']
    elif fault == 'missing_scenario': del inputs['policy']['bull']
    elif fault == 'short_horizon': inputs['policy']['base'].pop()
    elif fault == 'extra_driver': inputs['policy']['base'][0]['year'] = 1
    elif fault == 'missing_driver': del inputs['policy']['base'][0]['cost_ratio']
    elif fault in ('float', 'bool', 'nan', 'infinity', 'minus_one'):
        inputs['policy']['base'][0]['moutai_volume_growth'] = {
            'float': .1, 'bool': True, 'nan': 'NaN', 'infinity': 'Infinity', 'minus_one': '-1'}[fault]
    elif fault == 'cost': inputs['policy']['base'][0]['cost_ratio'] = '1.1'
    elif fault == 'history_float': inputs['annual']['parent_profit'][0] = 280.0
    elif fault == 'plan_bool': inputs['ledger']['plan']['horizon'] = True
    elif fault == 'retention': inputs['ledger']['plan']['explicit_retention'] = '.2'
    elif fault == 'held': inputs['ledger']['plan']['TIMING_DELAY']['withheld_fraction'] = '.2'
    elif fault == 'floor': inputs['ledger']['cases']['TIMING_DELAY']['base']['cash_floor'] = '900'
    elif fault == 'budget': inputs['ledger']['cases']['TIMING_DELAY']['bull']['project_budget'] = '10'
    elif fault == 'fund': inputs['ledger']['history']['known_uncalled_fund_commitment']['amount_cny'] = '10'
    elif fault == 'scope': inputs['ledger']['history']['scope'] = 'consolidated'
    elif fault == 'two_annual': inputs['ledger']['history']['periods']['FY2024'] = dict(operating_outflows='2000')
    elif fault == 'blocked': inputs['ledger']['cases']['TIMING_DELAY']['base']['blockers'] = ['TEST_ONLY unresolved']
    elif fault == 'branch': inputs['ledger']['cases']['TIMING_DELAY']['base']['branch'] = 'OTHER'
    elif fault == 'terminal': inputs['ledger']['cases']['TIMING_DELAY']['base']['terminal_growth'] = '.01'
    with pytest.raises(ValueError):
        build_product_operating_paths(**inputs)


@pytest.mark.parametrize('constraint', ['cash', 'retained', 'profit'])
def test_capacity_failure_preserves_policy_no_prices_or_inputs(inputs, constraint):
    if constraint == 'cash':
        for case in inputs['ledger']['cases']['TIMING_DELAY'].values():
            case['project_budget'] = '50000'
    elif constraint == 'retained': inputs['ledger']['history']['ttm']['parent_retained_profit_end'] = '0'
    else:
        for row in inputs['policy']['bear']: row['cost_ratio'] = '.99'
    before = deepcopy(inputs)
    result = build_product_operating_paths(**inputs)
    assert result['status'] == 'UNSUPPORTED' and result['failure']['year'] == 1
    assert result['failure']['scenario'] == 'bear'
    assert 'scenario_inputs' not in result and 'scenarios' not in result and 'valuation' not in result
    assert inputs == before
    if constraint == 'cash': assert D(result['failure']['cash_margin']) < 0
    if constraint == 'retained': assert D(result['failure']['retained_profit_margin']) < 0


def test_precision_independent_and_replayer_detects_changed_row(inputs):
    normal = build_product_operating_paths(**inputs)
    with localcontext() as ctx:
        ctx.prec = 6
        assert build_product_operating_paths(**inputs) == normal
    changed = deepcopy(normal['scenarios'])
    changed['bull']['annual_rows'][2]['project_cash'] = '1'
    with pytest.raises(ValueError, match='ledger mismatch'):
        replay_timing_delay_inputs(plan=inputs['ledger']['plan'], history=inputs['ledger']['history'],
            opening_book=inputs['opening_book'], scenarios=changed)


def test_inherited_project_fund_and_cash_return_all_recomputed(inputs):
    plan, history = inputs['ledger']['plan'], inputs['ledger']['history']
    plan['incremental_parent_cash_yield'] = '.02'
    plan['known_uncalled_fund_commitment']['amount_cny'] = '10'
    history['known_uncalled_fund_commitment']['amount_cny'] = '10'
    for case in inputs['ledger']['cases']['TIMING_DELAY'].values(): case['project_budget'] = '25'
    result = build_product_operating_paths(**inputs)
    assert result['status'] == 'CASH_CONTRACT_REPLAYED_NOT_ECONOMIC_APPROVAL'
    rows = result['scenarios']['base']['annual_rows']
    assert D(rows[0]['fund_capital_call']) == 10 and D(rows[1]['fund_capital_call']) == 0
    assert all(D(row['project_cash']) == 5 and D(row['fund_asset_at_cost']) == 10 for row in rows)
    assert D(rows[0]['incremental_parent_cash_income']) == 0
    assert D(rows[1]['incremental_parent_cash_income']) != 0
