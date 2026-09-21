"""Research-only annual scoring with explicit historical evidence selection."""
from datetime import date, timedelta, timezone
from decimal import Decimal

from .financial_quality import GENERAL_FIELDS, _accepted, evaluate_financial_quality
from .financial_institutions import provisional_financial_type
from .historical_asof import _timestamp, select_asof


MONEY_MULTIPLIERS = {'CNY': Decimal('1'), 'CNY 10K': Decimal('10000'),
                     'CNY 100M': Decimal('100000000')}


def annual_quality_asof(points, *, symbol, name, sector, period_label, decision_at):
    decision = _timestamp(decision_at)
    local_day = decision.astimezone(timezone(timedelta(hours=8))).date()
    period = date.fromisoformat(period_label)
    if period.isoformat() != period_label or (period.month, period.day) != (12, 31) or period >= local_day:
        raise ValueError('An ended annual reporting period is required')
    if provisional_financial_type(name, sector):
        raise ValueError('Historical institutional scoring is not supported by the general model')
    selected = []
    evidence = {}
    unit_errors = {}
    for field in GENERAL_FIELDS:
        rows = select_asof(points, symbol=symbol, field_name=field,
                           period_label=period_label, decision_at=decision_at)
        evidence[field] = rows
        # Equal values do not imply equal scope approval. Require every retained
        # version to pass the scoring gate instead of picking the favorable one.
        if rows and all(_accepted(row) for row in rows):
            row = dict(rows[0])
            if field in ('cash', 'interest_bearing_debt'):
                multiplier = MONEY_MULTIPLIERS.get(row['unit'])
                if multiplier is None:
                    unit_errors[field] = row['unit']
                    continue
                row['value'] = Decimal(str(row['value'])) * multiplier
                row['unit'] = 'CNY'
            elif row['unit'] != 'percent':
                unit_errors[field] = row['unit']
                continue
            selected.append(row)
    result = evaluate_financial_quality(symbol, name, sector, selected,
                                        evaluation_date=local_day)
    return {'symbol': symbol, 'decision_at': decision_at,
            'requested_period': period_label, 'score': result.database_row(),
            'evidence': evidence, 'unsupported_units': unit_errors, 'strategy_validated': False,
            'scope': 'Historical evidence-gated score only; no valuation or performance approval'}
