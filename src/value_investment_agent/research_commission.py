"""Dated Backtrader fee scenario; not verified personal-account costs."""
from datetime import date
from decimal import Decimal, localcontext
import math

from backtrader import CommInfoBase

from .historical_fees import statutory_components


class DatedResearchCommission(CommInfoBase):
    """Unrounded, per-fill minimum commission scenario for cash equity research.

    Bind a separate instance to each named daily price feed. Callers must use
    next-bar execution, no cheat-on-close, no shorting and no partial fills.
    These constraints are not enforced by a commission object alone.
    """

    params = (('stocklike', True), ('commtype', CommInfoBase.COMM_PERC), ('percabs', True))

    def __init__(self, price_feed, exchange, commission_rate, minimum_commission, scenario_id,
                 legacy_face_value_per_share=None, legacy_broker_rate=None,
                 legacy_broker_minimum=None, legacy_basis_ref=None):
        super().__init__()
        if exchange not in {'SSE', 'SZSE'}:
            raise ValueError('Unsupported research exchange')
        for value in (commission_rate, minimum_commission):
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError('Explicit finite nonnegative Decimal fee assumptions required')
        if commission_rate >= 1 or not math.isfinite(float(minimum_commission)):
            raise ValueError('Invalid fee scenario range')
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ValueError('A recorded research scenario ID is required')
        if price_feed is None:
            raise ValueError('Bind the actual price feed, not an unrelated calendar')
        if self.p.leverage != 1 or self.p.mult != 1 or self.p.interest != 0:
            raise ValueError('Only unlevered cash equity research is supported')
        self.price_feed = price_feed
        self.exchange = exchange
        self.commission_rate = commission_rate
        self.minimum_commission = minimum_commission
        self.scenario_id = scenario_id
        legacy = (legacy_face_value_per_share, legacy_broker_rate, legacy_broker_minimum, legacy_basis_ref)
        self.legacy = None
        if any(value is not None for value in legacy):
            for value in legacy[:3]:
                if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                    raise ValueError('Complete finite Decimal legacy fee assumptions required')
            if (legacy_face_value_per_share <= 0 or legacy_broker_rate >= 1
                    or not isinstance(legacy_basis_ref, str) or not legacy_basis_ref.strip()):
                raise ValueError('Legacy face value and recorded assumption reference required')
            if exchange != 'SSE':
                raise ValueError('Legacy Shanghai assumptions only apply to SSE')
            self.legacy = legacy

    def fee_breakdown(self, size, price):
        quantity, price = Decimal(str(size)), Decimal(str(price))
        if not quantity.is_finite() or quantity == 0 or quantity != quantity.to_integral_value():
            raise ValueError('A nonzero integral fill quantity is required')
        if not price.is_finite() or price <= 0:
            raise ValueError('A positive finite fill price is required')
        traded_on = self.price_feed.datetime.date(0)
        early = self.exchange == 'SSE' and traded_on < date(2015, 8, 1)
        if early and self.legacy is None:
            raise ValueError('Early Shanghai face value and broker-retained fee need separate evidence')
        with localcontext() as context:
            context.prec = 50
            turnover = abs(quantity) * price
            face = abs(quantity) * self.legacy[0] if early else None
            components = statutory_components(traded_on, self.exchange,
                                               'buy' if quantity > 0 else 'sell', turnover,
                                               traded_face_value=face)
            commission = max(turnover * self.commission_rate, self.minimum_commission)
            retained = max(face * self.legacy[1], self.legacy[2]) if early else Decimal(0)
            total = components['statutory_subtotal_unrounded_cny'] + commission + retained
        if not math.isfinite(float(total)):
            raise ValueError('Fees exceed engine numeric range')
        return {**components, 'scenario_id': self.scenario_id,
                'commission_rate_assumption': self.commission_rate,
                'minimum_commission_assumption': self.minimum_commission,
                'commission_unrounded_cny': commission, 'total_unrounded_cny': total,
                'legacy_broker_retained_assumption_cny': retained,
                'legacy_assumptions_applied': early,
                'legacy_basis_ref': self.legacy[3] if early else None,
                'legacy_rate_assumption_per_face_cny': self.legacy[1] if early else None,
                'legacy_minimum_assumption_cny': self.legacy[2] if early else None,
                'excluded': [x for x in components['excluded']
                             if not (early and x == 'broker_retained_legacy_transfer_fee')],
                'rounding_assumption': 'unrounded',
                'minimum_scope_assumption': 'per_fill',
                'exchange_charges_assumption': 'included_in_commission',
                'full_cost_verified': False}

    def _getcommission(self, size, price, pseudoexec):
        # Backtrader may estimate/confirm repeatedly; do not mutate cash or
        # append a trade ledger here. Only broker execution books the charge.
        if size == 0:
            return 0.0
        return float(self.fee_breakdown(size, price)['total_unrounded_cny'])
