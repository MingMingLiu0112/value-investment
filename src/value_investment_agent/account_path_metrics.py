"""Marked-account research metrics; no claim of executable net performance."""
from datetime import date
from decimal import Decimal as D
import math


def account_path_metrics(rows, *, opening_equity, opening_date):
    if not rows:
        raise ValueError('Empty account path')
    base = D(str(opening_equity))
    if not base.is_finite() or base <= 0:
        raise ValueError('Positive finite opening equity required')
    start = date.fromisoformat(opening_date)
    previous = None
    peak, peak_date = base, opening_date
    worst, worst_peak, trough = D(0), opening_date, opening_date
    recovery = None
    worst_peak_value = base
    exposures, cash_weights = [], []
    values = []
    for row in rows:
        day = date.fromisoformat(row['date'])
        if day < start or (previous is not None and day <= previous):
            raise ValueError('Unordered dates or pre-anchor observation')
        previous = day
        equity, cash, shares, close = (D(str(row[k])) for k in ('equity', 'cash', 'shares', 'close'))
        if any(not value.is_finite() for value in (equity, cash, shares, close)) or equity <= 0:
            raise ValueError('Invalid account observation')
        if shares < 0 or close <= 0:
            raise ValueError('Only long-only positive-price paths supported')
        if equity >= peak:
            peak, peak_date = equity, row['date']
        drawdown = D(1) - equity / peak
        if drawdown > worst:
            worst, worst_peak, trough = drawdown, peak_date, row['date']
            worst_peak_value, recovery = peak, None
        elif worst > 0 and recovery is None and equity >= worst_peak_value:
            recovery = row['date']
        exposures.append(shares * close / equity)
        cash_weights.append(cash / equity)
        values.append(equity)
    days = (previous - start).days
    ratio = values[-1] / base
    cagr = math.expm1(math.log(float(ratio)) * 365.25 / days) if days > 0 else None
    return {'opening_date': opening_date, 'first_observation': rows[0]['date'],
        'last_observation': rows[-1]['date'], 'observations': len(rows),
        'opening_equity': str(base), 'ending_equity': str(values[-1]),
        'marked_return': str(ratio - 1), 'annualized_marked_return_act36525': cagr,
        'max_drawdown': str(worst), 'drawdown_peak_date': worst_peak if worst else None,
        'drawdown_trough_date': trough if worst else None,
        'drawdown_recovery_date': recovery,
        'mean_session_stock_fraction': str(sum(exposures) / len(exposures)),
        'mean_session_cash_fraction': str(sum(cash_weights) / len(cash_weights)),
        'convention': 'Close-marked equity including recorded receivables. No external flows. Session-weighted exposure; cash excludes receivables. Segment opening is prior session close, positions carry through.',
        'net_performance_approved': False}
