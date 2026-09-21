"""Unrounded personal dividend liability under MOF 2012/85 and 2015/101.

This is a calculation component, not a tax-lot or broker settlement ledger.
The caller must establish the taxable base, net FIFO lot and settlement dates.
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


RULE_VERSION = 'cn-personal-dividend-tax-v1'


@dataclass(frozen=True)
class DividendTaxCalculation:
    rule_version: str
    policy: str
    effective_rate: Decimal
    taxable_income: Decimal
    initial_withholding: Decimal
    total_tax: Decimal
    additional_tax: Decimal


def _date(value: date) -> None:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError('An explicit settlement calendar date is required')


def _anniversary(acquired: date, *, months: int) -> date:
    index = acquired.year * 12 + acquired.month - 1 + months
    year, month = divmod(index, 12)
    try:
        return date(year, month + 1, acquired.day)
    except ValueError as exc:
        raise ValueError('Month-end/leap-day convention needs operational evidence') from exc


def calculate_dividend_tax(*, acquired: date, record_date: date,
                           disposal_settlement: date, taxable_income: Decimal,
                           account_type: str) -> DividendTaxCalculation:
    """Calculate a fully disposed, unrestricted SSE/SZSE personal FIFO lot.

    Income includes any *independently established* taxable stock dividend;
    it is not necessarily the cash payout. No rounding or debit date is assumed.
    Exact policy-start record dates await operational interpretation.
    """
    for day in (acquired, record_date, disposal_settlement):
        _date(day)
    if account_type != 'mainland_individual_unrestricted_sse_szse':
        raise ValueError('Unsupported or unknown account/share tax treatment')
    if not acquired <= record_date < disposal_settlement:
        raise ValueError('Requires acquisition, entitled record close, then disposal')
    if (not isinstance(taxable_income, Decimal) or not taxable_income.is_finite()
            or taxable_income < 0):
        raise ValueError('Known finite nonnegative Decimal taxable income required')
    if record_date <= date(2013, 1, 1) or record_date == date(2015, 9, 8):
        raise ValueError('Record-date tax regime is not covered by verified scope')
    new_policy = record_date > date(2015, 9, 8)
    # Holding ends the day BEFORE disposal settlement. Disposal on the
    # anniversary is exactly one month/year, so remains in the inclusive band.
    if disposal_settlement <= _anniversary(acquired, months=1):
        rate = Decimal('0.20')
    elif disposal_settlement <= _anniversary(acquired, months=12):
        rate = Decimal('0.10')
    else:
        rate = Decimal('0') if new_policy else Decimal('0.05')
    initial = taxable_income * (Decimal('0') if new_policy else Decimal('0.05'))
    total = taxable_income * rate
    return DividendTaxCalculation(RULE_VERSION,
                                  'MOF-2015-101' if new_policy else 'MOF-2012-85',
                                  rate, taxable_income, initial, total, total - initial)
