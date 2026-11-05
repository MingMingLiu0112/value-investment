"""TEST_ONLY cash/policy scope arithmetic; not issuer facts or approvals."""
from copy import deepcopy
from decimal import Decimal as D, localcontext
import json

import pytest

from value_investment_agent.domain.valuation.parent_cash_policy import (
    reconcile_parent_cash_statement, evaluate_cash_dividend_policy,
)


@pytest.fixture
def statement():
    return dict(symbol='600887', period_start='2026-01-01', period_end='2026-06-30',
        scope='issuer_parent_standalone', unit='CNY', currency='CNY', opening_cash_cny='100',
        cfo_cny='20', cfi_cny='-5', cff_cny='-10', fx_cny='1', reported_net_change_cny='6', closing_cash_cny='106')


@pytest.fixture
def policy_inputs():
    return dict(fiscal_year=2026, policy=dict(symbol='600887', scope='ordinary_cash_dividend_policy',
        currency='CNY', unit='ratio_and_CNY_per_share', fiscal_year_start=2025, fiscal_year_end=2027,
        profit_basis='consolidated_parent_attributable', minimum_payout_ratio='.5', minimum_dps_cny='1'),
        profit=dict(symbol='600887', period_start='2026-01-01', period_end='2026-12-31',
            scope='consolidated_parent_attributable', currency='CNY', unit='CNY', value='1000'),
        shares=dict(symbol='600887', fiscal_year=2026, as_of='2026-12-31',
            scope='ordinary_dividend_eligible_shares', unit='shares', value='600'))


def test_exact_cash_reconciliation_no_annualization_or_distribution_inference(statement):
    before = deepcopy(statement)
    result = reconcile_parent_cash_statement(statement=statement)
    assert result['computed_net_change_cny'] == '6'
    assert result['net_change_residual_cny'] == result['closing_cash_residual_cny'] == '0'
    assert result['annualized_cfo_cny'] is result['distributable_cash_cny'] is result['ordinary_cash_dividend_paid_cny'] is None
    assert statement == before and json.loads(json.dumps(result)) == result
    assert not any(result[key] for key in ('formal_eligibility', 'research_admitted', 'economic_approval', 'action_admitted'))


@pytest.mark.parametrize('fault', ['missing_fx', 'blank_fx', 'net_change', 'closing', 'group', 'currency',
    'unit', 'period', 'float', 'nan', 'combined_dividend', 'negative_cash'])
def test_parent_cash_missing_or_mismatched_inputs_rejected(statement, fault):
    if fault == 'missing_fx': del statement['fx_cny']
    elif fault == 'blank_fx': statement['fx_cny'] = None
    elif fault == 'net_change': statement['reported_net_change_cny'] = '7'
    elif fault == 'closing': statement['closing_cash_cny'] = '107'
    elif fault == 'group': statement['scope'] = 'consolidated'
    elif fault == 'currency': statement['currency'] = 'USD'
    elif fault == 'unit': statement['unit'] = 'CNY_thousands'
    elif fault == 'period': statement['period_end'] = '2025-12-31'
    elif fault == 'float': statement['cfo_cny'] = 20.0
    elif fault == 'nan': statement['cfo_cny'] = 'NaN'
    elif fault == 'combined_dividend': statement['ordinary_dividend_cny'] = statement['cff_cny']
    elif fault == 'negative_cash': statement['opening_cash_cny'] = '-100'
    with pytest.raises(ValueError): reconcile_parent_cash_statement(statement=statement)


@pytest.mark.parametrize('year,status', [(2024, 'POLICY_NOT_EFFECTIVE'), (2025, 'POLICY_THRESHOLD_RESEARCH_ONLY'),
    (2026, 'POLICY_THRESHOLD_RESEARCH_ONLY'), (2027, 'POLICY_THRESHOLD_RESEARCH_ONLY'), (2028, 'POLICY_EXPIRED')])
def test_explicit_policy_year_window_never_rolls_forward(policy_inputs, year, status):
    policy_inputs['fiscal_year'] = policy_inputs['shares']['fiscal_year'] = year
    policy_inputs['profit'].update(period_start=f'{year}-01-01', period_end=f'{year}-12-31')
    policy_inputs['shares']['as_of'] = f'{year}-12-31'
    result = evaluate_cash_dividend_policy(**policy_inputs)
    assert result['status'] == status
    assert result['policy_threshold_cny'] == ('600' if 2025 <= year <= 2027 else None)
    assert result['distributable_cash_cny'] is result['ordinary_cash_dividend_paid_cny'] is None
    assert not result['parent_legal_profit_inferred'] and not result['formal_eligibility']


def test_share_denominator_and_parent_legal_profit_are_explicit_not_derived(policy_inputs):
    before = deepcopy(policy_inputs)
    result = evaluate_cash_dividend_policy(**policy_inputs)
    assert result['ratio_threshold_cny'] == '500.0' and result['dps_threshold_cny'] == '600'
    assert policy_inputs == before
    policy_inputs['policy']['profit_basis'] = 'issuer_parent_standalone_profit'
    with pytest.raises(ValueError): evaluate_cash_dividend_policy(**policy_inputs)
    policy_inputs['profit']['scope'] = 'issuer_parent_standalone_profit'
    policy_inputs['profit']['value'] = '200'
    result = evaluate_cash_dividend_policy(**policy_inputs)
    assert result['profit']['value'] == '200' and result['ratio_threshold_cny'] == '100.0'


@pytest.mark.parametrize('fault', ['interim', 'scope', 'personal_shares', 'eps_shares', 'share_year',
    'fractional_shares', 'zero_shares', 'wrong_issuer', 'missing_profit', 'missing_ratio', 'mixed_cash_profit',
    'currency', 'ratio_float', 'ratio_bool', 'ratio_high', 'missing_start', 'open_end', 'reverse_years'])
def test_policy_strict_profit_share_and_term_contracts(policy_inputs, fault):
    p, profit, shares = policy_inputs['policy'], policy_inputs['profit'], policy_inputs['shares']
    if fault == 'interim': profit['period_end'] = '2026-06-30'
    elif fault == 'scope': profit['scope'] = 'group_net_profit'
    elif fault == 'personal_shares': shares['scope'] = 'personal_position'
    elif fault == 'eps_shares': shares['scope'] = 'weighted_average_eps_shares'
    elif fault == 'share_year': shares['fiscal_year'] = 2027
    elif fault == 'fractional_shares': shares['value'] = '600.1'
    elif fault == 'zero_shares': shares['value'] = '0'
    elif fault == 'wrong_issuer': profit['symbol'] = '600519'
    elif fault == 'missing_profit': profit['value'] = None
    elif fault == 'missing_ratio': del p['minimum_payout_ratio']
    elif fault == 'mixed_cash_profit': profit['scope'] = 'dividends_profit_and_interest_paid'
    elif fault == 'currency': profit['currency'] = 'USD'
    elif fault == 'ratio_float': p['minimum_payout_ratio'] = .5
    elif fault == 'ratio_bool': p['minimum_payout_ratio'] = True
    elif fault == 'ratio_high': p['minimum_payout_ratio'] = '1.1'
    elif fault == 'missing_start': del p['fiscal_year_start']
    elif fault == 'open_end': p['fiscal_year_end'] = None
    elif fault == 'reverse_years': p['fiscal_year_start'] = 2028
    with pytest.raises(ValueError): evaluate_cash_dividend_policy(**policy_inputs)


@pytest.mark.parametrize('profit', ['0', '-100'])
def test_nonpositive_profit_does_not_manufacture_capacity_or_dividend(policy_inputs, profit):
    policy_inputs['profit']['value'] = profit
    result = evaluate_cash_dividend_policy(**policy_inputs)
    assert result['status'] == 'NOT_ASSESSABLE_NON_POSITIVE_POLICY_PROFIT'
    assert result['policy_threshold_cny'] is None


def test_precision_isolation_and_json_safe(policy_inputs, statement):
    normal = evaluate_cash_dividend_policy(**policy_inputs)
    with localcontext() as ctx:
        ctx.prec = 6
        assert evaluate_cash_dividend_policy(**policy_inputs) == normal
        assert D(reconcile_parent_cash_statement(statement=statement)['computed_net_change_cny']) == 6
    assert json.loads(json.dumps(normal, allow_nan=False)) == normal
