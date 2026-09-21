from dataclasses import replace
from decimal import Decimal as D

import pytest

from value_investment_agent.scenario_valuation import (
    BridgeItem, ForecastYear, Terminal, value_scenario,
)


def inputs():
    return dict(
        forecast=[ForecastYear(2025, D('100'), D('0'), D('10'), D('10'), D('0'), D('.1'), ('synthetic',))],
        terminal=Terminal(D('100'), D('0'), D('.1'), D('.1'), ('synthetic',)),
        bridge=[], operating_exposure_ids=('industrial_operation',),
        ordinary_shares=D('100'), share_evidence_refs=('synthetic_shares',),
        currency='CNY', scenario_id='synthetic_not_company',
    )


def test_level_perpetuity_equals_closed_form_and_never_approves():
    result = value_scenario(**inputs())
    assert abs(result['operating_value'] - D('1000')) < D('1e-30')
    assert abs(result['per_share_value'] - D('10')) < D('1e-30')
    assert result['status'] == 'research_arithmetic_only'
    assert result['annual_cash_flows'][0]['wacc'] == D('.1')
    assert result['terminal_inputs']['growth'] == D('0')
    assert not result['strategy_approved'] and not result['evidence_authenticated']


def test_yearly_discount_factors_compound_and_terminal_reinvests():
    args = inputs()
    first = args['forecast'][0]
    args['forecast'].append(replace(first, year=2026, wacc=D('.2')))
    args['terminal'] = Terminal(D('120'), D('.02'), D('.1'), D('.12'), ('assumption',))
    result = value_scenario(**args)
    expected = D('100') / D('1.1') + (D('100') + D('960')) / D('1.32')
    assert abs(result['operating_value'] - expected) < D('1e-24')
    assert result['terminal_fcff'] == D('96')


def test_bridge_signs_and_scope():
    args = inputs()
    args['bridge'] = [BridgeItem(name, kind, D(value), (name,), ('evidence',))
                      for name, kind, value in [('cash', 'nonoperating_asset', '80'),
                                               ('finance_share', 'financial_equity', '40'),
                                               ('borrowings', 'debt', '200'),
                                               ('outside_owners', 'minority', '20'),
                                               ('options', 'dilution', '10')]]
    assert abs(value_scenario(**args)['ordinary_equity_value'] - D('890')) < D('1e-30')


@pytest.mark.parametrize('exposure', ['industrial_operation', 'same_financial_assets'])
def test_duplicate_declared_exposure_rejected(exposure):
    args = inputs()
    args['bridge'] = [BridgeItem('a', 'financial_equity', D('40'), (exposure,), ('evidence',)),
                      BridgeItem('b', 'nonoperating_asset', D('80'), (exposure,), ('evidence',))]
    with pytest.raises(ValueError, match='Double-counted'):
        value_scenario(**args)


@pytest.mark.parametrize('field,value', [('growth', '.1'), ('growth', '-.01'),
                                       ('roic', '0'), ('next_year_nopat', '-1'), ('wacc', 'NaN')])
def test_invalid_terminal_never_returns_price(field, value):
    args = inputs()
    args['terminal'] = replace(args['terminal'], **{field: D(value)})
    with pytest.raises(ValueError):
        value_scenario(**args)


def test_loss_has_no_automatic_tax_refund_and_working_capital_can_release():
    args = inputs()
    args['forecast'][0] = replace(args['forecast'][0], ebit=D('-20'), cash_tax_rate=D('.25'),
                                 working_capital_increase=D('-5'))
    row = value_scenario(**args)['annual_cash_flows'][0]
    assert row['nopat'] == D('-20') and row['fcff'] == D('-15')


@pytest.mark.parametrize('shares', ['0', '-1', '1.5', 'NaN'])
def test_share_denominator_invalid(shares):
    args = inputs()
    args['ordinary_shares'] = D(shares)
    with pytest.raises(ValueError):
        value_scenario(**args)


def test_negative_equity_is_preserved_not_floored_to_hide_shortfall():
    args = inputs()
    args['bridge'] = [BridgeItem('debt', 'debt', D('2000'), ('debt_claim',), ('evidence',))]
    result = value_scenario(**args)
    assert result['negative_equity_model_result']
    assert result['per_share_value'] < 0


def test_unordered_years_and_missing_evidence_rejected():
    args = inputs()
    args['forecast'].append(replace(args['forecast'][0], year=2027))
    with pytest.raises(ValueError, match='consecutive'):
        value_scenario(**args)
    args = inputs()
    args['terminal'] = replace(args['terminal'], evidence_refs=())
    with pytest.raises(ValueError, match='references'):
        value_scenario(**args)
