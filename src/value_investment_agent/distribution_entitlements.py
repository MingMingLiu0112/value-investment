"""Gross cash entitlement snapshots; caller supplies actual record-close holdings."""
from datetime import date
from decimal import Decimal

from .corporate_actions import validate_cash_distribution


class DistributionEntitlements:
    def __init__(self):
        self.snapshots = {}
        self.accrued = set()

    def record_close(self, event_id: str, event: dict, day: date, shares: int):
        per_share = validate_cash_distribution(event)
        if not event_id or day.isoformat() != event['record_date']:
            raise ValueError('Record-close event ID and date must match')
        if isinstance(shares, bool) or not isinstance(shares, int) or shares < 0:
            raise ValueError('Only known nonnegative integer holdings are supported')
        snapshot = {'symbol': event['symbol'], 'record_date': day,
                    'ex_date': date.fromisoformat(event['ex_date']),
                    'payment_date': date.fromisoformat(event['cash_payment_date']),
                    'shares': shares, 'gross_amount': per_share * Decimal(shares)}
        if event_id in self.snapshots and self.snapshots[event_id] != snapshot:
            raise ValueError('Conflicting record-close entitlement')
        self.snapshots[event_id] = snapshot

    def accrue(self, event_id: str, day: date, broker) -> bool:
        if event_id not in self.snapshots:
            raise ValueError('Record-close snapshot missing')
        snapshot = self.snapshots[event_id]
        if day != snapshot['ex_date']:
            raise ValueError('Receivable must be recognized on ex-date')
        result = broker.accrue_distribution(event_id, snapshot['gross_amount'])
        self.accrued.add(event_id)
        return result

    def pay(self, event_id: str, day: date, broker) -> bool:
        if event_id not in self.snapshots:
            raise ValueError('Record-close snapshot missing')
        snapshot = self.snapshots[event_id]
        if day != snapshot['payment_date']:
            raise ValueError('Payment must run on the actual payment date')
        if snapshot['payment_date'] > snapshot['ex_date'] and event_id not in self.accrued:
            raise ValueError('Delayed payment requires ex-date receivable recognition')
        return broker.credit_distribution(event_id, snapshot['gross_amount'])
