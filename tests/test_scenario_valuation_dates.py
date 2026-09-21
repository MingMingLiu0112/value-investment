from dataclasses import replace
from datetime import date
from decimal import Decimal as D
import math
import pytest
from test_scenario_valuation import inputs
from value_investment_agent.scenario_valuation import value_scenario


def dated():
    args = inputs()
    args['forecast'][0] = replace(args['forecast'][0], year=2026)
    return dict(**args, valuation_date=date(2026,9,9),
                cash_flow_dates=(date(2026,12,31),), timing_evidence_refs=('explicit-test-convention',))


def test_stub_cash_not_prorated_or_discounted_for_full_year():
    result = value_scenario(**dated())
    # Independent float power with the actual 113-day calendar interval.
    expected = 1100 / math.pow(1.1, 113/365)
    assert float(result['operating_value']) == pytest.approx(expected, rel=1e-13)
    assert result['annual_cash_flows'][0]['fcff'] == D('100')
    assert result['timing'] == 'explicit_dates_ACT_365F'
    assert not result['strategy_approved']


def test_leap_year_actual_day_count_and_term_structure():
    args = inputs()
    args['forecast'][0] = replace(args['forecast'][0], year=2024)
    args['forecast'].append(replace(args['forecast'][0], year=2025, wacc=D('.2')))
    result = value_scenario(**args, valuation_date=date(2023,12,31),
        cash_flow_dates=(date(2024,12,31), date(2025,12,31)), timing_evidence_refs=('fixture',))
    expected = 100/math.pow(1.1,366/365)+1100/(math.pow(1.1,366/365)*1.2)
    assert float(result['operating_value']) == pytest.approx(expected, rel=1e-13)


@pytest.mark.parametrize('dates', [(), (date(2026,9,9),), (date(2025,12,31),), None])
def test_missing_or_invalid_timing_rejected(dates):
    args=dated()
    args['cash_flow_dates']=dates
    with pytest.raises(ValueError):
        value_scenario(**args)


def test_no_implicit_timing_approval():
    args=dated()
    args['timing_evidence_refs']=()
    with pytest.raises(ValueError):
        value_scenario(**args)
