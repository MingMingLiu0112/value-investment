from datetime import date
from decimal import Decimal

import pytest

from value_investment_agent.research_broker import ResearchBroker


DAY = date(2015, 7, 17)


def broker(cash=1000):
    result = ResearchBroker(cash=cash)
    result.start()
    return result


def test_moutai_disclosed_initial_withholding_changes_cash_and_nav_once():
    b = broker()
    fundshares = b.fundshares
    b.credit_distribution('cninfo:1201268407:100', Decimal('437.40000'))
    assert b.accrue_tax('initial', Decimal('22.37000'), day=DAY, evidence_id='cninfo:1201268407:p2')
    assert b.getcash() == pytest.approx(1437.4)
    assert b.getvalue() == pytest.approx(1415.03)
    assert b.pay_tax('debit', 'initial', Decimal('22.37000'), day=DAY)
    assert b.getcash() == pytest.approx(1415.03)
    assert b.getvalue() == pytest.approx(1415.03)
    assert b.fundshares == fundshares
    assert not b.accrue_tax('initial', Decimal('22.37'), day=DAY, evidence_id='cninfo:1201268407:p2')
    assert not b.pay_tax('debit', 'initial', Decimal('22.37'), day=DAY)


def test_short_cash_retains_liability_partial_debit_does_not_double_expense():
    b = broker(10)
    b.accrue_tax('tax', Decimal('22.37'), day=DAY, evidence_id='fixture')
    with pytest.raises(ValueError, match='Insufficient'):
        b.pay_tax('failed', 'tax', Decimal('22.37'), day=DAY)
    assert b.tax_payments == {}
    assert b.tax_liabilities['tax'] == Decimal('22.37')
    b.pay_tax('partial', 'tax', Decimal('5'), day=DAY)
    assert b.getcash() == 5
    assert b.getvalue() == pytest.approx(-12.37)
    assert b.tax_liabilities['tax'] == Decimal('17.37')


def test_conflicting_or_unrecognized_debits_do_not_mutate():
    b = broker()
    with pytest.raises(ValueError, match='Recognized'):
        b.pay_tax('p', 'unknown', Decimal('1'), day=DAY)
    b.accrue_tax('tax', Decimal('20'), day=DAY, evidence_id='fixture')
    b.pay_tax('p', 'tax', Decimal('10'), day=DAY)
    with pytest.raises(ValueError, match='Conflicting'):
        b.pay_tax('p', 'tax', Decimal('11'), day=DAY)
    with pytest.raises(ValueError, match='exceeds'):
        b.pay_tax('p2', 'tax', Decimal('11'), day=DAY)
    with pytest.raises(ValueError, match='out of order'):
        b.pay_tax('p2', 'tax', Decimal('1'), day=date(2015, 7, 16))
    assert b.getcash() == 990
    assert b.getvalue() == 980


@pytest.mark.parametrize('amount', [Decimal('NaN'), Decimal('Infinity'), Decimal('-1'), 1.0])
def test_invalid_amount_rejected(amount):
    b = broker()
    with pytest.raises(ValueError):
        b.accrue_tax('tax', amount, day=DAY, evidence_id='fixture')
    assert b.tax_events == {}
    assert b.getcash() == b.getvalue() == 1000
