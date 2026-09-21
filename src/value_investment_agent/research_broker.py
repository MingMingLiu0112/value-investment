"""Pinned Backtrader extension for research income, not live brokerage."""
from decimal import Decimal
from datetime import date, datetime
import math

from backtrader.brokers import BackBroker


class ResearchBroker(BackBroker):
    """Caller must establish record-date entitlement and payment timing first."""

    def start(self):
        self.receivables = {}
        self.tax_liabilities = {}
        self.tax_events = {}
        self.tax_payments = {}
        super().start()
        self.income_events = {}

    def _get_value(self, datas=None, lever=False):
        value = super()._get_value(datas=datas, lever=lever)
        if datas is not None:
            return value
        receivable = float(sum(getattr(self, 'receivables', {}).values(), Decimal('0')))
        liability = float(sum(getattr(self, 'tax_liabilities', {}).values(), Decimal('0')))
        self._value += receivable - liability
        self._valuelever += receivable - liability
        self._fundval = self._value / self._fundshares
        return self._valuelever if lever else self._value

    @staticmethod
    def _validate_tax_posting(identity, amount, day):
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError('Tax posting identity required')
        if (not isinstance(amount, Decimal) or not amount.is_finite()
                or amount < 0 or not math.isfinite(float(amount))):
            raise ValueError('Tax amount must be a finite nonnegative Decimal')
        if not isinstance(day, date) or isinstance(day, datetime):
            raise ValueError('Explicit tax posting date required')

    def spendable_cash(self):
        return max(0.0, self.cash - float(sum(self.tax_liabilities.values(), Decimal('0'))))

    def _execute(self, order, ago=None, price=None, cash=None, position=None, dtcoc=None):
        reserve = float(sum(self.tax_liabilities.values(), Decimal('0')))
        if not reserve:
            return super()._execute(order, ago, price, cash, position, dtcoc)
        if ago is None:
            available = super()._execute(order, ago, price, cash - reserve, position, dtcoc)
            # check_submitted carries raw cash between orders. Negative buy
            # capacity must still trigger its Margin rejection; sales may repay debt.
            return available if available < 0 and order.isbuy() else available + reserve
        # Native execution still owns prices, commission, fills and order state.
        # Restore the reserve even if execution rejects or raises.
        self.cash -= reserve
        try:
            return super()._execute(order, ago, price, cash, position, dtcoc)
        finally:
            self.cash += reserve

    def accrue_tax(self, event_id, amount, *, day, evidence_id):
        """Recognize established tax expense; caller establishes amount and date."""
        self._validate_tax_posting(event_id, amount, day)
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            raise ValueError('Reviewed tax evidence required')
        record = {'amount': amount, 'day': day, 'evidence_id': evidence_id}
        if event_id in self.tax_events:
            if self.tax_events[event_id] != record:
                raise ValueError('Conflicting tax obligation')
            return False
        self.tax_events[event_id] = record
        self.tax_liabilities[event_id] = amount
        self._get_value()
        return True

    def pay_tax(self, payment_id, event_id, amount, *, day):
        """Record a specified full/partial debit without inventing collection timing."""
        self._validate_tax_posting(payment_id, amount, day)
        record = {'event_id': event_id, 'amount': amount, 'day': day}
        if payment_id in self.tax_payments:
            if self.tax_payments[payment_id] != record:
                raise ValueError('Conflicting tax payment')
            return False
        if event_id not in self.tax_events:
            raise ValueError('Recognized tax obligation required')
        prior = [x['day'] for x in self.tax_payments.values() if x['event_id'] == event_id]
        if day < max([self.tax_events[event_id]['day'], *prior]):
            raise ValueError('Tax payment date is out of order')
        if amount > self.tax_liabilities[event_id]:
            raise ValueError('Payment exceeds outstanding tax')
        if float(amount) > self.cash:
            raise ValueError('Insufficient cash; tax liability remains outstanding')
        # Tax is an expense, not an external withdrawal creating fund-share changes.
        self.cash -= float(amount)
        self.tax_liabilities[event_id] -= amount
        self.tax_payments[payment_id] = record
        self._get_value()
        return True

    def accrue_distribution(self, event_id: str, amount: Decimal) -> bool:
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError('Income event ID is required')
        if not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0 or not math.isfinite(float(amount)):
            raise ValueError('Invalid receivable amount')
        existing = self.income_events if event_id in self.income_events else self.receivables
        if event_id in existing:
            if existing[event_id] != amount:
                raise ValueError('Conflicting receivable amount')
            return False
        self.receivables[event_id] = amount
        self._get_value()
        return True

    def credit_distribution(self, event_id: str, amount: Decimal) -> bool:
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError('Income event ID is required')
        if not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0:
            raise ValueError('Income must be a finite nonnegative Decimal')
        if not math.isfinite(float(amount)):
            raise ValueError('Income exceeds broker numeric range')
        if event_id in self.income_events:
            if self.income_events[event_id] != amount:
                raise ValueError('Conflicting income under an existing event ID')
            return False
        if event_id in self.receivables and self.receivables[event_id] != amount:
            raise ValueError('Payment differs from accrued entitlement')
        # add_cash creates fund shares and would classify income as a deposit.
        self.cash += float(amount)
        self.receivables.pop(event_id, None)
        self.income_events[event_id] = amount
        self._get_value()
        return True
