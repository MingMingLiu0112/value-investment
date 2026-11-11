"""TEST_ONLY arithmetic contracts, not forecasts or source admission."""
from copy import deepcopy
from decimal import Decimal as D, localcontext
import json
import pytest

from test_source_native_candidate_v2 import test_only_ledger as make_ledger
from value_investment_agent.domain.valuation.operating_realization_erosion_v1 import build_erosion_bear


@pytest.fixture
def inputs():
    annual = dict(operating_revenue=['1000','1000'], cost_of_sales=['200','200'],
        taxes_surcharges=['50','50'], selling=['50','50'], administration=['50','50'],
        research=['10','10'], profit_before_tax=['400','400'], income_tax=['100','100'],
        parent_profit=['280','280'], ex_parent_profit=['270','270'])
    interim = dict(operating_revenue=['500','500'], cost_of_sales=['120','100'],
        taxes_surcharges=['25','25'], selling=['25','25'], administration=['25','25'],
        research=['5','5'], profit_before_tax=['190','200'], income_tax=['50','50'],
        parent_profit=['130','140'], ex_parent_profit=['125','135'])
    return dict(annual=annual, interim=interim, wine_revenue_yoy_pct='-1.08',
        wine_volume_yoy_pct='2.13', ledger=make_ledger(D('1000'),'2026-06-30'), opening_book='1000')


def test_compound_not_linear_and_old_base_bull_exact(inputs):
    old = deepcopy(inputs)
    result = build_erosion_bear(**inputs)
    assert inputs == old
    assert result['status'] == 'CASH_CONTRACT_REPLAYED_NOT_ECONOMIC_APPROVAL'
    for name in ('base','bull'):
        assert json.dumps(result['scenarios'][name]) == json.dumps(old['ledger']['cases']['TIMING_DELAY'][name])
    with localcontext() as context:
        context.prec = 48
        factor = D('.9892')/D('1.0213')
        for year, row in enumerate(result['operating_rows'], 1):
            assert abs(D(row['revenue'])-1000*factor**year) < D('1e-40')
            assert abs(D(row['cost'])-D(row['revenue'])*D('.24')) < D('1e-40')
        assert D(result['operating_rows'][4]['revenue']) != 1000*factor
        cash_rows = result['scenarios']['bear']['annual_rows']
        assert D(cash_rows[1]['released']) == D(cash_rows[0]['newly_withheld'])
        assert D(cash_rows[-1]['delayed_close']) == 0


@pytest.mark.parametrize('damage', ['missing', 'float', 'nan', 'volume', 'recovery', 'negative_cost'])
def test_invalid_or_non_erosion_inputs_fail_closed(inputs, damage):
    if damage == 'missing': del inputs['annual']['income_tax']
    elif damage == 'float': inputs['wine_volume_yoy_pct'] = 2.13
    elif damage == 'nan': inputs['annual']['parent_profit'][0] = 'NaN'
    elif damage == 'volume': inputs['wine_volume_yoy_pct'] = '-100'
    elif damage == 'recovery': inputs['wine_revenue_yoy_pct'] = '10'
    else: inputs['interim']['cost_of_sales'][0] = '-1'
    with pytest.raises(ValueError): build_erosion_bear(**inputs)


@pytest.mark.parametrize('failure', ['cash', 'retained', 'profit'])
def test_unsupported_has_constraints_not_prices(inputs, failure):
    if failure == 'cash':
        for case in inputs['ledger']['cases']['TIMING_DELAY'].values(): case['project_budget'] = '50000'
    elif failure == 'retained': inputs['ledger']['history']['ttm']['parent_retained_profit_end'] = '0'
    else: inputs['interim']['cost_of_sales'][0] = '490'
    result = build_erosion_bear(**inputs)
    assert result['status'] == 'UNSUPPORTED'
    assert result['failure']['year'] == 1
    assert 'scenario_inputs' not in result and 'valuation' not in result


def test_precision_isolation(inputs):
    normal = build_erosion_bear(**inputs)
    with localcontext() as context:
        context.prec = 6
        assert build_erosion_bear(**inputs) == normal
