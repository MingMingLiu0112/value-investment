from datetime import date
from decimal import Decimal

import pytest

from value_investment_agent.distribution_entitlements import DistributionEntitlements


EVENT = {'symbol': '601088', 'record_date': '2017-07-07', 'ex_date': '2017-07-10',
         'cash_payment_date': '2017-07-10', 'cash_amount': '2.970', 'per_shares': '1',
         'cash_per_share': '2.970', 'amount_basis': 'implemented_gross_entitlement',
         'evidence': [{'test_fixture': True}]}


class IncomeSink:
    def __init__(self):
        self.events = {}

    def credit_distribution(self, key, amount):
        if key in self.events:
            assert self.events[key] == amount
            return False
        self.events[key] = amount
        return True


def test_payment_uses_frozen_entitlement_not_payment_day_holdings():
    ledger, sink = DistributionEntitlements(), IncomeSink()
    ledger.record_close('event', EVENT, date(2017, 7, 7), 100)
    assert ledger.pay('event', date(2017, 7, 10), sink)
    assert sink.events['event'] == Decimal('297')
    assert not ledger.pay('event', date(2017, 7, 10), sink)


def test_no_record_date_holding_means_no_dividend():
    ledger, sink = DistributionEntitlements(), IncomeSink()
    ledger.record_close('event', EVENT, date(2017, 7, 7), 0)
    ledger.pay('event', date(2017, 7, 10), sink)
    assert sink.events['event'] == 0


def test_delayed_payment_cannot_hide_missing_ex_date_receivable():
    from value_investment_agent.research_broker import ResearchBroker

    event = {**EVENT, 'cash_payment_date': '2017-07-12'}
    ledger = DistributionEntitlements()
    broker = ResearchBroker(cash=1000)
    broker.start()
    ledger.record_close('delayed', event, date(2017, 7, 7), 100)
    with pytest.raises(ValueError, match='ex-date receivable'):
        ledger.pay('delayed', date(2017, 7, 12), broker)
    assert broker.getcash() == 1000
    assert ledger.accrue('delayed', date(2017, 7, 10), broker)
    assert broker.getcash() == 1000
    assert broker.getvalue() == 1297
    assert ledger.pay('delayed', date(2017, 7, 12), broker)
    assert broker.getcash() == 1297
    assert broker.getvalue() == 1297
    assert not ledger.pay('delayed', date(2017, 7, 12), broker)


def test_failed_accrual_does_not_authorize_later_payment():
    class FailedSink:
        def accrue_distribution(self, key, amount):
            raise RuntimeError('Accounting failed')

    ledger = DistributionEntitlements()
    ledger.record_close('failed', {**EVENT, 'cash_payment_date': '2017-07-12'},
                        date(2017, 7, 7), 100)
    with pytest.raises(RuntimeError):
        ledger.accrue('failed', date(2017, 7, 10), FailedSink())
    with pytest.raises(ValueError, match='ex-date receivable'):
        ledger.pay('failed', date(2017, 7, 12), IncomeSink())


@pytest.mark.parametrize('day', [date(2017, 7, 7), date(2017, 7, 11)])
def test_no_early_or_silently_late_payment(day):
    ledger = DistributionEntitlements()
    ledger.record_close('event', EVENT, date(2017, 7, 7), 100)
    with pytest.raises(ValueError):
        ledger.pay('event', day, IncomeSink())


def test_missing_and_conflicting_snapshot_fail():
    ledger = DistributionEntitlements()
    with pytest.raises(ValueError):
        ledger.pay('event', date(2017, 7, 10), IncomeSink())
    ledger.record_close('event', EVENT, date(2017, 7, 7), 100)
    with pytest.raises(ValueError):
        ledger.record_close('event', EVENT, date(2017, 7, 7), 200)


@pytest.mark.parametrize('shares', [None, True, -1, 1.5])
def test_unknown_or_unsupported_holdings_rejected(shares):
    with pytest.raises(ValueError):
        DistributionEntitlements().record_close('event', EVENT, date(2017, 7, 7), shares)
