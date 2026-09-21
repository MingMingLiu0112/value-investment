"""Integer share distributions on an explicit event clock; research only."""
from copy import deepcopy
from datetime import date
from decimal import Decimal

from .research_broker import ResearchBroker


class ShareActionResearchBroker(ResearchBroker):
    """Economic shares book before ex-date trades; new shares stay sale-locked.

    Cash dividends/taxes are separate. Built-in trade analyzers do not receive
    these non-trade adjustments and cannot be used as an adjusted trade ledger.
    """

    def start(self):
        super().start()
        self.share_events = {}
        self._share_bindings = {}

    def record_share_distribution(self, event_id, data, clock, event):
        dates = {key: date.fromisoformat(event[key]) for key in
                 ('record_date', 'ex_date', 'listing_date')}
        if not dates['record_date'] < dates['ex_date'] <= dates['listing_date']:
            raise ValueError('Invalid share distribution chronology')
        if not isinstance(event_id, str) or not event_id.strip() or not event.get('evidence'):
            raise ValueError('Share event ID and primary evidence are required')
        if clock.datetime.date(0) != dates['record_date']:
            raise ValueError('Snapshot must be taken at the actual record-date close')
        ratio = Decimal(str(event['shares_per_share']))
        if not ratio.is_finite() or ratio <= 0:
            raise ValueError('Positive finite distribution ratio required')
        shares = self.getposition(data).size
        if type(shares) is not int or shares < 0:
            raise ValueError('Only nonnegative integer long positions are supported')
        added = Decimal(shares) * ratio
        if added != added.to_integral_value():
            raise ValueError('Fractional-share allocation requires separate evidence; no rounding')
        snapshot = {'event': deepcopy(event), 'record_shares': shares,
                    'added_shares': int(added), 'credited': False, 'released': False}
        if event_id in self.share_events:
            previous = self.share_events[event_id]
            previous_data, previous_clock = self._share_bindings[event_id]
            if previous != snapshot or previous_data is not data or previous_clock is not clock:
                raise ValueError('Conflicting share event snapshot')
            return False
        self.share_events[event_id] = snapshot
        self._share_bindings[event_id] = (data, clock)
        return True

    def sellable_shares(self, data):
        locked = sum(row['added_shares'] for key, row in self.share_events.items()
                     if self._share_bindings[key][0] is data and row['credited'] and not row['released'])
        return max(0, self.getposition(data).size - locked)

    def next(self):
        for key, row in self.share_events.items():
            data, clock = self._share_bindings[key]
            day = clock.datetime.date(0)
            event = row['event']
            ex_date = date.fromisoformat(event['ex_date'])
            if not row['credited'] and day >= ex_date:
                if day != ex_date:
                    raise ValueError('Event clock skipped share ex-date')
                if row['added_shares'] and data.datetime.date(0) != day:
                    raise ValueError('Missing ex-date price mark; cannot value added shares at stale price')
                position = self.getposition(data)
                if position.size < 0:
                    raise ValueError('Share distribution cannot adjust a short position')
                size = position.size + row['added_shares']
                if row['added_shares']:
                    # Preserve aggregate cost; no cash flow or external deposit.
                    position.fix(size, position.size * position.price / size)
                row['credited'] = True
            if row['credited'] and day >= date.fromisoformat(event['listing_date']):
                row['released'] = True
        super().next()

    def _try_exec(self, order):
        if order.issell() and abs(order.executed.remsize) > self.sellable_shares(order.data):
            order.reject()
            order.addinfo(rejection_reason='Insufficient unlocked shares; no short sales')
            self.notify(order)
            self._ococheck(order)
            self._bracketize(order, cancel=True)
            return
        super()._try_exec(order)
