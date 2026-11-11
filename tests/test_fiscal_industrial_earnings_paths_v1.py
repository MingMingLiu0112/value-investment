"""TEST_ONLY seasonal/fiscal arithmetic, not issuer research or source approval."""
from copy import deepcopy
from decimal import Decimal as D, localcontext
import json

import pytest

from value_investment_agent.domain.valuation.fiscal_industrial_earnings_paths_v1 import build_fiscal_industrial_earnings_paths


@pytest.fixture
def inputs():
    def record(start, end, revenue, costs, pbt, tax, nci, parent, asset, credit):
        names = ('cost_of_sales', 'taxes_surcharges', 'selling', 'administration', 'research')
        lines = dict(zip(names, costs))
        lines.update(operating_revenue=revenue, profit_before_tax=pbt, income_tax=tax,
            minority_profit=nci, parent_profit=parent, asset_impairment=asset, credit_impairment=credit,
            net_profit=str(D(pbt)-D(tax)))
        return dict(symbol='000001', period_start=start, period_end=end, scope='consolidated',
            unit='CNY', currency='CNY', accounting_basis_id='TEST_ONLY_COMPARABLE_FLOW_BASIS', lines=lines)
    historical = dict(
        FY2025=record('2025-01-01', '2025-12-31', '1000', ['600', '10', '150', '30', '10'],
            '180', '40', '-10', '150', '-20', '-5'),
        H12025=record('2025-01-01', '2025-06-30', '400', ['240', '4', '60', '12', '4'],
            '100', '20', '-2', '82', '-10', '-1'),
        H12026=record('2026-01-01', '2026-06-30', '450', ['270', '4.5', '67.5', '13.5', '4.5'],
            '70', '15', '-3', '58', '-5', '-2'))
    stub = dict(revenue_growth='.02', commercial_margin='.1', inventory_impairment_ratio='.01',
        goodwill_impairment_cny='1', other_asset_impairment_cny='1', other_pbt_cny='6',
        tax_research_rate='.2', signed_nci_cny='-1')
    stubs = {name: dict(stub) for name in ('bear', 'base', 'bull')}
    stubs['bear'].update(revenue_growth='-.01', commercial_margin='.08', signed_nci_cny='0')
    stubs['bull'].update(revenue_growth='.04', commercial_margin='.12', signed_nci_cny='0')
    annual = dict(stub, revenue_growth='.03', commercial_margin='.11')
    return dict(historical=historical, stub_scenarios=stubs,
        scenarios={name: [dict(annual, year=year) for year in range(2027, 2032)] for name in stubs})


def test_seasonal_difference_stub_mixed_fiscal_and_own_annual_revenue(inputs):
    before = deepcopy(inputs)
    result = build_fiscal_industrial_earnings_paths(**inputs)
    h2 = result['historical_h2_2025']
    assert h2['classification'] == 'DERIVED_FY_MINUS_H1_FROM_SAME_BASIS'
    assert not h2['full_year'] and h2['period_start'] == '2025-07-01'
    assert h2['lines']['operating_revenue'] == '600'
    assert h2['lines']['parent_profit'] == '68' and h2['lines']['credit_impairment'] == '-4'
    stub = result['research_h2_2026']['base']
    assert D(stub['lines']['operating_revenue']) == 612  # Not current H1*2, nor TTM.
    assert D(stub['lines']['profit_before_tax']) == D('59.08')
    assert D(stub['lines']['income_tax']) == D('12.016')
    assert D(stub['lines']['parent_profit']) == D('48.064')
    base = result['fy2026_research_base']['base']
    assert base['classification'] == 'MIXED_ACTUAL_H1_AND_RESEARCH_H2'
    assert base['full_year'] and base['confidence'] == 'LOW'
    assert D(base['lines']['operating_revenue']) == 1062
    assert D(base['lines']['parent_profit']) == D('106.064')
    assert 'credit_impairment' in base['unmodelled_historical_line_names']
    assert 'credit_impairment' not in base['lines']
    for name in ('bear', 'base', 'bull'):
        opening = D(result['fy2026_research_base'][name]['lines']['operating_revenue'])
        with localcontext() as ctx:
            ctx.prec = 48
            for step, row in enumerate(result['scenarios'][name]['rows'], 1):
                year = 2026+step
                assert row['year'] == row['inputs']['year'] == row['fiscal_year'] == year
                assert row['projection_step'] == step
                assert row['period_start'] == f'{year}-01-01' and row['period_end'] == f'{year}-12-31'
                assert row['full_year'] and row['classification'] == 'RESEARCH_ASSUMPTION' and row['confidence'] == 'LOW'
                assert D(row['revenue_cny']) == opening*D('1.03')**step
                assert D(row['group_pbt_cny'])-D(row['income_tax_cny'])-D(row['signed_nci_cny']) == D(row['parent_profit_cny'])
                assert 'change_from_historical_parent' not in row
                assert 'change_from_fy2026_research_parent' in row
    assert inputs == before and json.loads(json.dumps(result, allow_nan=False)) == result
    assert not any(result[key] for key in ('formal_eligibility', 'economic_approval', 'research_admitted', 'price_admitted'))
    assert 'valuation' not in result and 'cash' not in result and result['action'] == 'no_order'


def test_scenario_stub_change_only_affects_its_own_fiscal_path(inputs):
    old = build_fiscal_industrial_earnings_paths(**inputs)
    inputs['stub_scenarios']['bear']['revenue_growth'] = '-.10'
    changed = build_fiscal_industrial_earnings_paths(**inputs)
    for name in ('base', 'bull'):
        assert old['scenarios'][name] == changed['scenarios'][name]
        assert old['fy2026_research_base'][name] == changed['fy2026_research_base'][name]
    assert old['scenarios']['bear'] != changed['scenarios']['bear']


def test_computational_cost_partition_changes_no_aggregate_forecast(inputs):
    old = build_fiscal_industrial_earnings_paths(**inputs)
    for record in inputs['historical'].values():
        cost = D(record['lines']['cost_of_sales'])
        record['lines']['cost_of_sales'] = str(cost-10)
        record['lines']['selling'] = str(D(record['lines']['selling'])+10)
    changed = build_fiscal_industrial_earnings_paths(**inputs)
    assert changed['scenarios'] == old['scenarios']
    assert changed['research_h2_2026']['base']['cost_component_scope'].startswith('COMPUTATIONAL_')


@pytest.mark.parametrize('fault', ['ttm_key', 'missing_period', 'date', 'scope', 'unit', 'symbol', 'basis',
    'missing_basis', 'line_set', 'parent_identity', 'net_identity', 'negative_h2_cost', 'nan', 'float',
    'missing_stub_scenario', 'missing_stub_driver', 'extra_stub_driver', 'bad_stub_growth', 'negative_loss',
    'bad_stub_tax', 'missing_annual_scenario', 'rolling_year', 'short_path', 'bool_year', 'annual_nan'])
def test_missing_mixed_restated_or_invalid_inputs_rejected(inputs, fault):
    historical = inputs['historical']
    if fault == 'ttm_key': historical['TTM2026'] = historical.pop('FY2025')
    elif fault == 'missing_period': del historical['H12025']
    elif fault == 'date': historical['H12025']['period_end'] = '2025-12-31'
    elif fault == 'scope': historical['H12026']['scope'] = 'issuer_parent_standalone'
    elif fault == 'unit': historical['FY2025']['unit'] = 'CNY_thousands'
    elif fault == 'symbol': historical['FY2025']['symbol'] = '600887'
    elif fault == 'basis': historical['H12025']['accounting_basis_id'] = 'TEST_ONLY_RESTATED_UNRECONCILED'
    elif fault == 'missing_basis': historical['H12025']['accounting_basis_id'] = ''
    elif fault == 'line_set': del historical['H12025']['lines']['credit_impairment']
    elif fault == 'parent_identity': historical['H12026']['lines']['parent_profit'] = '59'
    elif fault == 'net_identity': historical['FY2025']['lines']['net_profit'] = '139'
    elif fault == 'negative_h2_cost': historical['H12025']['lines']['research'] = '11'
    elif fault == 'nan': historical['FY2025']['lines']['operating_revenue'] = 'NaN'
    elif fault == 'float': historical['FY2025']['lines']['income_tax'] = 40.0
    elif fault == 'missing_stub_scenario': del inputs['stub_scenarios']['base']
    elif fault == 'missing_stub_driver': del inputs['stub_scenarios']['base']['signed_nci_cny']
    elif fault == 'extra_stub_driver': inputs['stub_scenarios']['base']['year'] = 2026
    elif fault == 'bad_stub_growth': inputs['stub_scenarios']['base']['revenue_growth'] = '-1'
    elif fault == 'negative_loss': inputs['stub_scenarios']['base']['goodwill_impairment_cny'] = '-1'
    elif fault == 'bad_stub_tax': inputs['stub_scenarios']['base']['tax_research_rate'] = '1.1'
    elif fault == 'missing_annual_scenario': del inputs['scenarios']['bull']
    elif fault == 'rolling_year': inputs['scenarios']['base'][0]['year'] = 1
    elif fault == 'short_path': inputs['scenarios']['base'].pop()
    elif fault == 'bool_year': inputs['scenarios']['base'][0]['year'] = True
    elif fault == 'annual_nan': inputs['scenarios']['base'][0]['commercial_margin'] = 'NaN'
    with pytest.raises(ValueError): build_fiscal_industrial_earnings_paths(**inputs)


def test_precision_isolation_and_missing_optional_net_profit_not_filled(inputs):
    for record in inputs['historical'].values(): del record['lines']['net_profit']
    result = build_fiscal_industrial_earnings_paths(**inputs)
    assert 'net_profit' not in result['historical_h2_2025']['lines']
    with localcontext() as ctx:
        ctx.prec = 6
        assert build_fiscal_industrial_earnings_paths(**inputs) == result
