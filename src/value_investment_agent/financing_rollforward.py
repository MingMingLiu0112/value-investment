"""Arithmetic checks for financing-liability note rows, not investment approval."""
from decimal import Decimal, InvalidOperation

AMOUNTS = ('opening', 'cash_increase', 'noncash_increase',
           'cash_decrease', 'noncash_decrease', 'closing')


def reconciles(row):
    try:
        values = {key: Decimal(str(row[key])) for key in AMOUNTS}
        if any(not value.is_finite() for value in values.values()):
            return False
        expected = (values['opening'] + values['cash_increase'] + values['noncash_increase']
                    - values['cash_decrease'] - values['noncash_decrease'])
        return expected == values['closing']
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return False


def reconciles_table(rows, total):
    if not rows or not reconciles(total) or not all(reconciles(row) for row in rows):
        return False
    return all(sum(Decimal(str(row[key])) for row in rows) == Decimal(str(total[key]))
               for key in AMOUNTS)
