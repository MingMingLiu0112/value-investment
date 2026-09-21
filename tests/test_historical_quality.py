"""Synthetic time-boundary contracts, not historical financial verification."""
from decimal import Decimal
import pytest

from value_investment_agent.historical_quality import annual_quality_asof
from test_financial_quality import general_points


def facts():
    return [dict(p, symbol='600001', period_label='2014-12-31',
                 raw_file_hash='synthetic-test-only',
                 unit='CNY' if p['field_name'] in ('cash', 'interest_bearing_debt') else 'percent',
                 timestamp_precision='timestamp', availability_verified=True,
                 published_at='2015-03-21T08:00:00+08:00',
                 available_at='2015-03-21T08:00:00+08:00') for p in general_points()]


def score(points, at='2015-05-01T00:00:00+08:00'):
    return annual_quality_asof(points, symbol='600001', name='Manufacturing',
                              sector=None, period_label='2014-12-31', decision_at=at)


def test_historical_report_is_scored_at_historical_date():
    result = score(facts())
    assert result['score']['total_score'] == Decimal('100')
    assert result['strategy_validated'] is False
    assert len(result['evidence']) == 9


def test_future_publication_cannot_score():
    assert score(facts(), '2015-03-20T00:00:00+08:00')['score']['total_score'] is None


def test_expired_report_stays_blocked_at_later_decision():
    assert score(facts(), '2016-05-01T00:00:00+08:00')['score']['total_score'] is None


def test_unverified_equal_version_cannot_be_hidden_by_verified_one():
    points = facts()
    points.append(dict(points[0], metadata={'automatic_cross_source_verification': False}))
    assert score(points)['score']['total_score'] is None


def test_later_revision_does_not_change_earlier_score():
    points = facts()
    points.append(dict(points[0], value=Decimal('1'), source_id='later-revision',
                       published_at='2015-06-01T00:00:00+08:00',
                       available_at='2015-06-01T00:00:00+08:00'))
    assert score(points)['score']['total_score'] == Decimal('100')
    assert score(points, '2015-07-01T00:00:00+08:00')['score']['total_score'] == Decimal('85')


@pytest.mark.parametrize('period', ['2015-12-31', '2014-06-30'])
def test_future_or_interim_period_rejected(period):
    with pytest.raises(ValueError, match='annual'):
        annual_quality_asof(facts(), symbol='600001', name=None, sector=None,
                           period_label=period, decision_at='2015-05-01T00:00:00+08:00')


def test_bank_cannot_use_general_historical_score():
    with pytest.raises(ValueError, match='institutional'):
        annual_quality_asof([], symbol='600036', name='招商银行', sector='银行',
                           period_label='2014-12-31', decision_at='2015-05-01T00:00:00+08:00')


@pytest.mark.parametrize('field,unit', [('roe', 'ratio'), ('cash', 'USD'),
                                      ('interest_bearing_debt', 'unknown')])
def test_unsupported_unit_blocks_score(field, unit):
    points = facts()
    next(p for p in points if p['field_name'] == field)['unit'] = unit
    result = score(points)
    assert result['score']['total_score'] is None
    assert result['unsupported_units'] == {field: unit}


def test_money_units_normalized_without_mutating_evidence():
    points = facts()
    cash = next(p for p in points if p['field_name'] == 'cash')
    debt = next(p for p in points if p['field_name'] == 'interest_bearing_debt')
    cash.update(value=Decimal('0.012'), unit='CNY 10K')
    debt.update(value=Decimal('0.000001'), unit='CNY 100M')
    result = score(points)
    assert result['score']['total_score'] == Decimal('100')
    assert result['score']['calculation_details']['values']['cash'] == '120.000'
    assert result['evidence']['cash'][0]['unit'] == 'CNY 10K'
    assert cash['value'] == Decimal('0.012')
