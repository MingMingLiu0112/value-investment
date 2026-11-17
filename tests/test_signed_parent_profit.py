"""Signed-NCI arithmetic only; historical check figures are not source admission."""
from copy import deepcopy
from decimal import Decimal as D, localcontext
import json

import pytest

from test_operating_product_paths import inputs
from value_investment_agent.domain.valuation.operating_product_paths import build_product_operating_paths
from value_investment_agent.domain.valuation.signed_parent_profit import build_signed_parent_profit_path


@pytest.mark.parametrize('pbt,tax,nci,parent', [
    ('12993830374.42', '1479919620.42', '-51255743.81', '11565166497.81'),
    ('7314474445.37', '1790782129.57', '-234935781.99', '5758628097.79'),
    ('12034018510.64', '2231858993.45', '-321157466.50', '10123316983.69'),
])
def test_disclosed_signed_nci_arithmetic_fy_h1_ttm_not_source_or_forecast_approval(pbt, tax, nci, parent):
    # User-supplied historical check figures, not a PDF-source verification test.
    result = build_signed_parent_profit_path(years=[2026], group_pbt_cny=[pbt],
        tax_assumptions=[dict(basis='amount_cny', value=tax)], signed_nci_cny=[nci], currency='CNY')
    row = result['rows'][0]
    assert row['parent_profit_cny'] == parent
    assert D(row['bridge_residual_cny']) == 0
    assert result['action'] == 'no_order' and not result['economic_approval']
    assert result['normalized_parent_profit_cny'] is None


def test_explicit_signed_nci_convergence_and_tax_basis_per_year_no_history_ratio():
    args = dict(years=[2027, 2028, 2029], group_pbt_cny=['100', '120', '140'],
        tax_assumptions=[dict(basis='amount_cny', value='25'), dict(basis='effective_rate', value='.25'),
                         dict(basis='amount_cny', value='35')],
        signed_nci_cny=['-10', '-5', '2'], currency='CNY')
    before = deepcopy(args)
    result = build_signed_parent_profit_path(**args)
    assert [D(row['parent_profit_cny']) for row in result['rows']] == [D('85'), D('95'), D('103')]
    assert [D(row['income_tax_cny']) for row in result['rows']] == [D('25'), D('30'), D('35')]
    assert args == before and json.loads(json.dumps(result, allow_nan=False)) == result
    with localcontext() as ctx:
        ctx.prec = 6
        assert build_signed_parent_profit_path(**args) == result


@pytest.mark.parametrize('pbt,tax_basis,tax,nci,parent', [
    ('-100', 'amount_cny', '0', '-10', '-90'),
    ('-100', 'effective_rate', '.25', '0', '-75'),
    ('100', 'amount_cny', '-5', '10', '95'),
    ('0', 'amount_cny', '0', '0', '0'),
])
def test_signed_losses_and_explicit_tax_credit_not_automatically_normalized(pbt, tax_basis, tax, nci, parent):
    result = build_signed_parent_profit_path(years=[1], group_pbt_cny=[pbt],
        tax_assumptions=[dict(basis=tax_basis, value=tax)], signed_nci_cny=[nci], currency='CNY')
    assert D(result['rows'][0]['parent_profit_cny']) == D(parent)
    assert 'scenario_inputs' not in result and 'valuation' not in result


@pytest.mark.parametrize('fault', ['currency', 'empty', 'year_bool', 'year_text', 'year_zero', 'gap', 'duplicate',
    'pbt_length', 'nci_length', 'tax_length', 'implicit_nci', 'implicit_tax', 'tax_extra', 'tax_basis',
    'pbt_float', 'tax_bool', 'nci_float', 'pbt_nan', 'tax_infinite', 'nci_nan', 'rate_high', 'rate_negative'])
def test_signed_parent_profit_requires_explicit_finite_year_matched_inputs(fault):
    args = dict(years=[2027], group_pbt_cny=['100'],
        tax_assumptions=[dict(basis='amount_cny', value='25')], signed_nci_cny=['-10'], currency='CNY')
    if fault == 'currency': args['currency'] = 'USD'
    elif fault == 'empty': args['years'] = []
    elif fault == 'year_bool': args['years'] = [True]
    elif fault == 'year_text': args['years'] = ['2027']
    elif fault == 'year_zero': args['years'] = [0]
    elif fault == 'gap': args['years'] = [2027, 2029]
    elif fault == 'duplicate': args['years'] = [2027, 2027]
    elif fault == 'pbt_length': args['group_pbt_cny'] = []
    elif fault == 'nci_length': args['signed_nci_cny'] = []
    elif fault == 'tax_length': args['tax_assumptions'] = []
    elif fault == 'implicit_nci': args['signed_nci_cny'] = [None]
    elif fault == 'implicit_tax': args['tax_assumptions'] = [None]
    elif fault == 'tax_extra': args['tax_assumptions'][0]['inferred'] = True
    elif fault == 'tax_basis': args['tax_assumptions'][0]['basis'] = 'infer_from_history'
    elif fault == 'pbt_float': args['group_pbt_cny'] = [100.0]
    elif fault == 'tax_bool': args['tax_assumptions'][0]['value'] = True
    elif fault == 'nci_float': args['signed_nci_cny'] = [-10.0]
    elif fault == 'pbt_nan': args['group_pbt_cny'] = ['NaN']
    elif fault == 'tax_infinite': args['tax_assumptions'][0]['value'] = 'Infinity'
    elif fault == 'nci_nan': args['signed_nci_cny'] = ['NaN']
    elif fault in ('rate_high', 'rate_negative'):
        args['tax_assumptions'][0] = dict(basis='effective_rate', value='1.01' if fault == 'rate_high' else '-.01')
    with pytest.raises(ValueError):
        build_signed_parent_profit_path(**args)


def test_original_product_path_still_rejects_negative_nci_parent_share_over_one(inputs):
    for statement in (inputs['annual'], inputs['interim']):
        statement['parent_profit'] = ['10000', '10000']
    with pytest.raises(ValueError, match='parent attribution'):
        build_product_operating_paths(**inputs)
