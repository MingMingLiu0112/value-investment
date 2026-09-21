from datetime import date, datetime
from decimal import Decimal

import pytest

from value_investment_agent.historical_fees import statutory_components


def fees(day, exchange='SSE', side='sell', **kwargs):
    return statutory_components(date.fromisoformat(day), exchange, side, Decimal('100000'), **kwargs)


@pytest.mark.parametrize('day,stamp,transfer', [
    ('2015-08-03', '100', '2'), ('2022-04-28', '100', '2'),
    ('2022-04-29', '100', '1'), ('2023-08-25', '100', '1'),
    ('2023-08-28', '50', '1'), ('2025-12-31', '50', '1'),
])
def test_effective_date_boundaries(day, stamp, transfer):
    result = fees(day)
    assert result['stamp_duty_unrounded_cny'] == Decimal(stamp)
    assert result['csdc_transfer_unrounded_cny'] == Decimal(transfer)
    assert not result['full_cost_verified']


@pytest.mark.parametrize('exchange', ['SSE', 'SZSE'])
def test_buy_is_not_stamp_taxed_but_transfer_is_bilateral(exchange):
    result = fees('2023-08-28', exchange, 'buy')
    assert result['stamp_rate'] == 0
    assert result['csdc_transfer_unrounded_cny'] == 1
    assert 'stamp-2008' in result['source_urls']


def test_early_shanghai_uses_explicit_face_value_not_turnover():
    result = fees('2015-07-31', traded_face_value=Decimal('1000'))
    assert result['csdc_transfer_unrounded_cny'] == Decimal('0.3')
    assert result['transfer_basis'] == 'traded_face_value_cny'
    with pytest.raises(ValueError):
        fees('2015-07-31')


def test_early_shenzhen_uses_turnover_and_retains_unrounded_amount():
    result = fees('2015-01-05', 'SZSE')
    assert result['csdc_transfer_unrounded_cny'] == Decimal('2.55')
    result = statutory_components(date(2025, 1, 2), 'SSE', 'buy', Decimal('1000.55'))
    assert result['csdc_transfer_unrounded_cny'] == Decimal('0.0100055')


@pytest.mark.parametrize('day', [date(2014, 12, 31), date(2026, 1, 1), datetime(2023, 8, 28), '2023-08-28'])
def test_reject_uncovered_dates_and_implicit_timezone(day):
    with pytest.raises(ValueError):
        statutory_components(day, 'SSE', 'buy', Decimal('100'))


@pytest.mark.parametrize('amount', [Decimal('0'), Decimal('-1'), Decimal('NaN'), Decimal('Infinity'), 100.0])
def test_invalid_turnover_rejected(amount):
    with pytest.raises(ValueError):
        statutory_components(date(2023, 8, 28), 'SSE', 'buy', amount)


def test_unsupported_exchange_and_side_rejected():
    with pytest.raises(ValueError):
        fees('2023-08-28', 'BSE')
    with pytest.raises(ValueError):
        fees('2023-08-28', side='short')
