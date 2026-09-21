"""Point-in-time trailing profit research; no implicit per-share conversion."""
from calendar import monthrange
from datetime import date
from decimal import Decimal

from .historical_asof import select_asof


def trailing_profit(points, *, symbol, period_end, decision_at):
    end = date.fromisoformat(period_end)
    if end.month not in (3, 6, 9) or end.day != monthrange(end.year, end.month)[1]:
        raise ValueError('A cumulative Q1, half-year or Q3 period end is required')
    periods = (period_end, f'{end.year - 1}-12-31',
               f'{end.year - 1}-{end.month:02d}-{end.day:02d}')
    inputs = []
    for period in periods:
        rows = select_asof(points, symbol=symbol,
                           field_name='parent_attributable_net_income',
                           period_label=period, decision_at=decision_at)
        if not rows:
            raise ValueError('Missing verified available profit for ' + period)
        for row in rows:
            meta = row.get('metadata') or {}
            expected_start = period[:4] + '-01-01'
            if (meta.get('period_start') != expected_start
                    or meta.get('scope') != 'consolidated_parent_attributable'
                    or meta.get('ttm_comparability_verified') is not True
                    or not meta.get('accounting_basis')
                    or not meta.get('comparability_evidence_id')):
                raise ValueError('Unverified cumulative period or accounting comparability')
        inputs.append(rows)
    all_rows = [row for group in inputs for row in group]
    bases = {(row['unit'], row['metadata']['accounting_basis'],
              row['metadata']['comparability_evidence_id']) for row in all_rows}
    if len(bases) != 1:
        raise ValueError('Incompatible units, accounting basis or comparison evidence')
    unit = all_rows[0]['unit']
    if unit not in ('CNY', 'CNY thousand', 'CNY million'):
        raise ValueError('Explicit supported monetary unit required; EPS is not profit')
    current, annual, previous = (Decimal(str(rows[0]['value'])) for rows in inputs)
    return {'symbol': symbol, 'period_end': period_end, 'decision_at': decision_at,
            'field_name': 'parent_attributable_net_income_ttm',
            'value': current + annual - previous, 'unit': unit,
            'formula': 'current_ytd + prior_annual - prior_ytd',
            'evidence': inputs, 'backtest_ready': False,
            'limitation': 'Profit only; share basis and trading assumptions not validated'}
