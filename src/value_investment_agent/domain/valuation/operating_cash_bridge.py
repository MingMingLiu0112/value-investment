"""Reconcile disclosed cash-flow changes, not sustainable cash forecasts."""
from decimal import Decimal


def operating_cash_change_bridge(current: dict[str, Decimal], prior: dict[str, Decimal]) -> dict:
    required = {'sales_receipts', 'interest_receipts', 'tax_refunds', 'other_receipts',
                'purchases_paid', 'employees_paid', 'taxes_paid', 'other_payments',
                'inflow_total', 'outflow_total', 'cfo'}
    if set(current) != required or set(prior) != required:
        raise ValueError('cash bridge requires every explicit component, not zero substitutes')
    positive = ['sales_receipts', 'interest_receipts', 'tax_refunds', 'other_receipts']
    negative = ['purchases_paid', 'employees_paid', 'taxes_paid', 'other_payments']
    for values in (current, prior):
        if any(not value.is_finite() for value in values.values()):
            raise ValueError('cash bridge values must be finite')
        if (sum(values[key] for key in positive) != values['inflow_total']
                or sum(values[key] for key in negative) != values['outflow_total']
                or values['inflow_total'] - values['outflow_total'] != values['cfo']):
            raise ValueError('cash statement components do not reconcile exactly')
    contributions = {key: (current[key] - prior[key]) * (1 if key in positive else -1)
                     for key in positive + negative}
    change = current['cfo'] - prior['cfo']
    if sum(contributions.values()) != change:
        raise ValueError('cash change bridge mismatch')
    return dict(cfo_change_cny=str(change), contributions_cny={key: str(value) for key, value in contributions.items()},
                reconciliation='EXACT', sustainable_cash_proven=False, forecast_approved=False, action='no_order')
