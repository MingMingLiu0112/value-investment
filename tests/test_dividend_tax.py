from datetime import date
from decimal import Decimal

import pytest

from value_investment_agent.dividend_tax import calculate_dividend_tax


def calc(acquired='2016-01-15', record='2016-01-20', sold='2016-02-15', income='100'):
    return calculate_dividend_tax(
        acquired=date.fromisoformat(acquired), record_date=date.fromisoformat(record),
        disposal_settlement=date.fromisoformat(sold), taxable_income=Decimal(income),
        account_type='mainland_individual_unrestricted_sse_szse')


@pytest.mark.parametrize('sold,rate', [
    ('2016-02-15', '0.20'), ('2016-02-16', '0.10'),
    ('2017-01-15', '0.10'), ('2017-01-16', '0'),
])
def test_inclusive_natural_anniversaries(sold, rate):
    result = calc(sold=sold)
    assert result.effective_rate == Decimal(rate)
    assert result.initial_withholding == 0
    assert result.additional_tax == Decimal('100') * Decimal(rate)


def test_pre_reform_entitlement_is_not_reclassified_at_later_sale():
    result = calc(acquired='2015-01-15', record='2015-07-16', sold='2016-01-16')
    assert result.policy == 'MOF-2012-85'
    assert result.initial_withholding == Decimal('5')
    assert result.total_tax == Decimal('5')
    assert result.additional_tax == 0


def test_older_policy_initial_and_deferred_tax_are_separate():
    result = calc(acquired='2015-07-01', record='2015-07-16', sold='2015-07-20')
    assert result.initial_withholding == Decimal('5')
    assert result.total_tax == Decimal('20')
    assert result.additional_tax == Decimal('15')


def test_actual_old_acquisition_counts_for_new_policy():
    result = calc(acquired='2014-06-15', record='2015-09-09', sold='2015-09-10')
    assert result.total_tax == 0


@pytest.mark.parametrize('acquired,record,sold', [
    ('2016-01-31', '2016-02-01', '2016-03-01'),
    ('2016-02-29', '2016-03-01', '2017-03-01'),
    ('2015-01-15', '2015-09-08', '2015-10-01'),
    ('2012-01-15', '2013-01-01', '2013-02-01'),
    ('2016-01-15', '2016-01-20', '2016-01-20'),
])
def test_unverified_calendar_or_ineligible_entitlement_rejected(acquired, record, sold):
    with pytest.raises(ValueError):
        calc(acquired, record, sold)


@pytest.mark.parametrize('income', ['NaN', 'Infinity', '-1'])
def test_unknown_or_invalid_income_is_not_zero(income):
    with pytest.raises(ValueError):
        calc(income=income)


def test_does_not_round_each_share_before_account_aggregation():
    result = calc(income='27.673')
    assert result.total_tax == Decimal('5.53460')
