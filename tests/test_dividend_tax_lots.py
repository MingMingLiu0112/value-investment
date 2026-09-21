from datetime import date
from decimal import Decimal

import pytest

from value_investment_agent.dividend_tax_lots import ACCOUNT, DividendTaxLots, TaxDistribution


def day(value):
    return date.fromisoformat(value)


def ledger():
    return DividendTaxLots(account_id='explicit-hypothetical-account', symbol='600519',
                           account_type=ACCOUNT)


def event(record='2016-02-10', amount='2', identity='d1'):
    return TaxDistribution(identity, day(record), Decimal(amount), 'explicit-test-fixture')


def test_net_zero_turnover_keeps_old_lot_and_fifo_partial_sales():
    book = ledger()
    book.close(day('2015-01-15'), bought=100, sold=0)
    book.close(day('2016-02-01'), bought=100, sold=0)
    book.close(day('2016-02-10'), bought=100, sold=100, distributions=(event(),))
    result = book.close(day('2016-02-15'), bought=0, sold=150)
    old, new = result['disposals']
    assert (old['shares'], new['shares']) == (100, 50)
    assert old['taxes'][0]['calculation'].additional_tax == 0
    assert new['taxes'][0]['calculation'].additional_tax == Decimal('20')
    remaining = book.close(day('2016-03-02'), bought=0, sold=50)
    assert remaining['disposals'][0]['taxes'][0]['calculation'].additional_tax == Decimal('10')
    assert remaining['closing_shares'] == 0


def test_record_close_applies_net_transfers_before_entitlement():
    book = ledger()
    book.close(day('2016-02-01'), bought=200, sold=0)
    result = book.close(day('2016-02-10'), bought=100, sold=150, distributions=(event(),))
    assert result['entitlements'][0]['shares'] == 150
    assert result['entitlements'][0]['taxable_income'] == Decimal('300')
    assert result['disposals'][0]['taxes'] == []


def test_idempotent_replay_and_output_mutation_do_not_change_history():
    book = ledger()
    first = book.close(day('2016-02-01'), bought=100, sold=0)
    first['closing_shares'] = -1
    assert book.close(day('2016-02-01'), bought=100, sold=0)['closing_shares'] == 100
    before = book.snapshot()
    with pytest.raises(ValueError, match='Conflicting'):
        book.close(day('2016-02-01'), bought=200, sold=0)
    assert book.snapshot() == before


def test_unverified_second_lot_rolls_back_entire_disposal():
    book = ledger()
    book.close(day('2016-01-15'), bought=100, sold=0)
    book.close(day('2016-01-31'), bought=100, sold=0)
    book.close(day('2016-02-10'), bought=0, sold=0, distributions=(event(),))
    before = book.snapshot()
    with pytest.raises(ValueError, match='Month-end'):
        book.close(day('2016-03-02'), bought=0, sold=200)
    assert book.snapshot() == before


def test_each_distribution_keeps_own_tax_regime_on_partial_disposal():
    book = ledger()
    book.close(day('2015-06-15'), bought=100, sold=0)
    book.close(day('2015-07-16'), bought=0, sold=0,
               distributions=(event('2015-07-16', '2', 'old'),))
    book.close(day('2015-10-15'), bought=0, sold=0,
               distributions=(event('2015-10-15', '3', 'new'),))
    result = book.close(day('2016-06-16'), bought=0, sold=50)
    old, new = [x['calculation'] for x in result['disposals'][0]['taxes']]
    assert old.total_tax == Decimal('5')
    assert old.additional_tax == 0
    assert new.total_tax == 0
    assert result['closing_shares'] == 50


def test_duplicate_distribution_and_oversale_do_not_commit():
    book = ledger()
    book.close(day('2016-02-01'), bought=100, sold=0)
    before = book.snapshot()
    with pytest.raises(ValueError, match='Duplicate'):
        book.close(day('2016-02-10'), bought=0, sold=0, distributions=(event(), event()))
    with pytest.raises(ValueError, match='exceeds'):
        book.close(day('2016-02-10'), bought=0, sold=101)
    assert book.snapshot() == before
