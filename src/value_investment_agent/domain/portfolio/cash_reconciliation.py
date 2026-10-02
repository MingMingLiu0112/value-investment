"""Independently reconcile research-ledger cash without approving trades."""
from decimal import Decimal


def reconcile_cash_journal(journal: list[dict], initial_cash: Decimal) -> dict:
    def amount(value):
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError('cash reconciliation requires finite nonnegative amounts')
        return number

    cash = amount(initial_cash)
    receivable = Decimal('0')
    totals = dict(buy_principal=Decimal('0'), sell_principal=Decimal('0'),
                  fees=Decimal('0'), dividend_accrued=Decimal('0'), dividend_paid=Decimal('0'))
    rows = []
    seen = set()
    entitlements = {}
    previous_date = None
    if not journal:
        raise ValueError('cash reconciliation requires a journal')
    for row in journal:
        day = row['date']
        if previous_date is not None and day <= previous_date:
            raise ValueError('cash journal must be chronological and unique')
        previous_date = day
        opening_cash, opening_receivable = cash, receivable
        movement = {key: Decimal('0') for key in totals}
        for event in row.get('cash_events', []):
            kind = event['kind']
            identity = (event['event_id'], kind)
            if kind not in {'record', 'bonus_credit', 'accrual', 'payment'} or identity in seen:
                raise ValueError('unknown or repeated cash event')
            seen.add(identity)
            if kind in {'record', 'bonus_credit'}:
                continue
            value = amount(event['amount_cny'])
            if kind == 'accrual':
                entitlements[event['event_id']] = value
                receivable += value
                movement['dividend_accrued'] += value
            else:
                if entitlements.get(event['event_id']) != value:
                    raise ValueError('payment must match its own accrued dividend')
                del entitlements[event['event_id']]
                receivable -= value
                cash += value
                movement['dividend_paid'] += value
                if receivable < 0:
                    raise ValueError('payment exceeds dividend receivables')
        fill = row.get('fill')
        if fill is not None:
            if type(fill['quantity']) is not int or fill['quantity'] <= 0:
                raise ValueError('fill requires positive integer shares')
            principal = amount(fill['price']) * fill['quantity']
            fee = amount(fill['fee_cny'])
            if fill['side'] == 'buy':
                cash -= principal + fee
                movement['buy_principal'] = principal
            elif fill['side'] == 'sell':
                cash += principal - fee
                movement['sell_principal'] = principal
            else:
                raise ValueError('unknown fill side')
            movement['fees'] = fee
        if cash != amount(row['cash_cny']) or receivable != amount(row['receivable_cny']):
            raise ValueError(f'cash/receivable reconciliation mismatch on {day}')
        for key, value in movement.items():
            totals[key] += value
        if any(movement.values()):
            rows.append(dict(date=day, opening_cash_cny=str(opening_cash),
                opening_receivable_cny=str(opening_receivable),
                **{key + '_cny': str(value) for key, value in movement.items()},
                closing_cash_cny=str(cash), closing_receivable_cny=str(receivable)))
    return dict(status='MATCH', sessions_checked=len(journal),
        initial_cash_cny=str(initial_cash), ending_cash_cny=str(cash),
        ending_receivable_cny=str(receivable),
        totals={key + '_cny': str(value) for key, value in totals.items()}, movements=rows,
        scope='GROSS_RESEARCH_LEDGER_CASH_ONLY', tax_treatment_verified=False, action='no_order')
