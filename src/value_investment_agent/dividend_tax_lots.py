"""Single-account, single-security tax lots; no cash debits or trade matching.

MOF 2012/85 section III requires end-of-day net changes and FIFO disposal.
Corporate-action changes to tax lots must be resolved before using this ledger.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .dividend_tax import _date, calculate_dividend_tax


ACCOUNT = 'mainland_individual_unrestricted_sse_szse'


@dataclass(frozen=True)
class TaxDistribution:
    event_id: str
    record_date: date
    taxable_per_share: Decimal
    evidence_id: str

    def validate(self):
        _date(self.record_date)
        if not self.event_id.strip() or not self.evidence_id.strip():
            raise ValueError('Distribution identity and reviewed evidence required')
        if (not isinstance(self.taxable_per_share, Decimal)
                or not self.taxable_per_share.is_finite() or self.taxable_per_share < 0):
            raise ValueError('Verified finite nonnegative taxable base required')
        if self.record_date <= date(2013, 1, 1) or self.record_date == date(2015, 9, 8):
            raise ValueError('Unverified record-date policy boundary')


@dataclass
class _Lot:
    acquired: date
    shares: int
    distributions: list[TaxDistribution] = field(default_factory=list)


class DividendTaxLots:
    def __init__(self, *, account_id: str, symbol: str, account_type: str):
        if not account_id.strip() or not symbol.strip() or account_type != ACCOUNT:
            raise ValueError('Explicit supported account and security required')
        self.account_id, self.symbol = account_id, symbol
        self._lots = []
        self._days = {}
        self._events = set()

    def snapshot(self):
        return deepcopy({'account_id': self.account_id, 'symbol': self.symbol,
                         'lots': self._lots, 'days': self._days})

    def close(self, day: date, *, bought: int, sold: int,
              distributions: tuple[TaxDistribution, ...] = ()):
        """Apply net settled market transfers, then snapshot record-close lots.

        Caller supplies complete settled daily trades for this account/security.
        Outputs are unrounded tax calculations, NOT dated payment instructions.
        """
        _date(day)
        for quantity in (bought, sold):
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
                raise ValueError('Known nonnegative integer settled quantities required')
        distributions = tuple(distributions)
        for event in distributions:
            event.validate()
            if event.record_date != day:
                raise ValueError('Distribution must match this record close')
        request = (bought, sold, distributions)
        if day in self._days:
            if self._days[day]['request'] != request:
                raise ValueError('Conflicting replay of settled day')
            return deepcopy(self._days[day]['result'])
        if self._days and day <= max(self._days):
            raise ValueError('Settlement days must be chronological')
        event_ids = [event.event_id for event in distributions]
        if len(set(event_ids)) != len(event_ids) or self._events.intersection(event_ids):
            raise ValueError('Duplicate distribution identity')

        # Stage the entire day: a rejected tax calculation cannot consume a lot.
        lots = deepcopy(self._lots)
        delta = bought - sold
        result = {'day': day, 'net_shares': delta, 'disposals': [], 'entitlements': []}
        if delta > 0:
            lots.append(_Lot(day, delta))
        elif delta < 0:
            remaining = -delta
            if remaining > sum(lot.shares for lot in lots):
                raise ValueError('Net disposal exceeds known tax inventory')
            for lot in lots:
                quantity = min(remaining, lot.shares)
                if not quantity:
                    continue
                taxes = []
                for event in lot.distributions:
                    calculation = calculate_dividend_tax(
                        acquired=lot.acquired, record_date=event.record_date,
                        disposal_settlement=day,
                        taxable_income=event.taxable_per_share * quantity,
                        account_type=ACCOUNT)
                    taxes.append({'event_id': event.event_id,
                                  'evidence_id': event.evidence_id,
                                  'calculation': calculation})
                result['disposals'].append({'acquired': lot.acquired, 'shares': quantity,
                                            'taxes': taxes})
                lot.shares -= quantity
                remaining -= quantity
            lots = [lot for lot in lots if lot.shares]
        for event in distributions:
            for lot in lots:
                lot.distributions.append(event)
                income = event.taxable_per_share * lot.shares
                initial = income * (Decimal('0.05') if day < date(2015, 9, 8) else Decimal('0'))
                result['entitlements'].append({'event_id': event.event_id,
                    'evidence_id': event.evidence_id, 'acquired': lot.acquired,
                    'shares': lot.shares, 'taxable_income': income,
                    'initial_withholding_calculated': initial})
        result['closing_shares'] = sum(lot.shares for lot in lots)
        self._lots = lots
        self._events.update(event_ids)
        self._days[day] = {'request': request, 'result': deepcopy(result)}
        return result
