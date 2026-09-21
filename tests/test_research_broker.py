from decimal import Decimal

import pytest

pytest.importorskip('backtrader')
from value_investment_agent.research_broker import ResearchBroker


def broker():
    result = ResearchBroker()
    result.setcash(10000)
    result.start()
    return result


def test_distribution_is_income_not_external_deposit():
    b = broker()
    shares = b.fundshares
    assert b.credit_distribution('reviewed-event-100-shares', Decimal('297.00'))
    assert b.getcash() == pytest.approx(10297)
    assert b.getvalue() == pytest.approx(10297)
    assert b.fundshares == shares
    assert b.fundvalue == pytest.approx(102.97)


def test_duplicate_event_does_not_double_credit_and_conflict_fails():
    b = broker()
    b.credit_distribution('event', Decimal('297'))
    assert not b.credit_distribution('event', Decimal('297.00'))
    with pytest.raises(ValueError):
        b.credit_distribution('event', Decimal('298'))
    assert b.getcash() == 10297


@pytest.mark.parametrize('value', [Decimal('NaN'), Decimal('Infinity'), Decimal('-1'),
                                   Decimal('1E999'), 297.0])
def test_invalid_income_rejected_without_mutation(value):
    b = broker()
    with pytest.raises(ValueError):
        b.credit_distribution('event', value)
    assert b.getcash() == 10000
    assert b.income_events == {}


def test_external_deposit_remains_distinct():
    b = broker()
    b.add_cash(297)
    b._get_value()
    assert b.fundvalue == pytest.approx(100)
    assert b.fundshares == pytest.approx(102.97)


def test_receivable_is_not_spendable_and_payment_does_not_double_income():
    b = broker()
    assert b.accrue_distribution('event', Decimal('100'))
    assert b.getcash() == 10000
    assert b.getvalue() == 10100
    b._get_value()
    assert b.getvalue() == 10100
    assert b.fundvalue == 101
    assert not b.accrue_distribution('event', Decimal('100'))
    with pytest.raises(ValueError):
        b.credit_distribution('event', Decimal('101'))
    assert b.getcash() == 10000
    b.credit_distribution('event', Decimal('100'))
    assert b.getcash() == b.getvalue() == 10100
    assert b.receivables == {}
    assert not b.accrue_distribution('event', Decimal('100'))
    assert b.fundshares == 100
