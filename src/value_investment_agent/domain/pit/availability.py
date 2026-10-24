"""Statutory disclosure deadlines as a conservative availability calendar.

Why the deadline and not the real announcement date
---------------------------------------------------
The real `published_at` is better when it exists (see
`infrastructure/data/pit_extract.extract_disclosure_dates`). But it does not
exist for every row, and where it is missing a caller is tempted to fall back to
"the data is in the table, so it must have been known". That fallback is exactly
how look-ahead enters a backtest.

The statutory deadline is a floor: no company may publish later than it. So
deferring every fact to the deadline can only push a signal later in time, and a
signal that fires later cannot have read the future. This makes the rule safe by
construction rather than by audit.

Scope note
----------
This module is pure stdlib. `domain/` must not import Excel, database drivers,
network clients, operations, scripts or test fixtures.
"""

from __future__ import annotations

from datetime import date

SCHEMA_VERSION = "pit-availability-v1"

# Statutory disclosure deadline (month, day), keyed by the month a report period
# ends. Per 上市公司信息披露管理办法: annual within four months of the fiscal year
# end, interim within two months, first and third quarter within one month.
DEADLINE_MONTH_DAY: dict[int, tuple[int, int]] = {
    3: (4, 30),    # Q1  -> 04-30
    6: (8, 31),    # H1  -> 08-31
    9: (10, 31),   # Q3  -> 10-31
    12: (4, 30),   # FY  -> 04-30 of the following year
}

# Report-period end dates, in the `YYYYMMDD` form used by the public endpoints.
PERIOD_SUFFIXES: tuple[str, ...] = ("0331", "0630", "0930", "1231")

ANNUAL_PERIOD_SUFFIX = "1231"


def split_period(period: str) -> tuple[int, int, int]:
    """Split `YYYYMMDD` (also accepts `YYYY-MM-DD`) into (year, month, day)."""
    digits = period.replace("-", "")
    if len(digits) != 8 or not digits.isdigit():
        raise ValueError(f"report period must be YYYYMMDD or YYYY-MM-DD: {period!r}")
    return int(digits[:4]), int(digits[4:6]), int(digits[6:8])


def available_at(period: str) -> date:
    """Earliest date on which `period` may be assumed public, conservatively."""
    year, month, _ = split_period(period)
    if month not in DEADLINE_MONTH_DAY:
        raise ValueError(f"not a statutory report period month: {period!r} (month={month})")
    deadline_month, deadline_day = DEADLINE_MONTH_DAY[month]
    if month == 12:
        year += 1
    return date(year, deadline_month, deadline_day)


def is_available(period: str, as_of: date) -> bool:
    """True only when the deadline has already passed on `as_of`."""
    return available_at(period) <= as_of


def report_periods(start_year: int, end_year: int, as_of: date | None = None,
                   annual_only: bool = False) -> list[str]:
    """Report periods in range that are already public as of `as_of`.

    A period is emitted only when both its end date and its statutory deadline
    are in the past, so no partially-disclosed period can slip into a sample.
    """
    as_of = as_of or date.today()
    suffixes = (ANNUAL_PERIOD_SUFFIX,) if annual_only else PERIOD_SUFFIXES
    out: list[str] = []
    for year in range(start_year, end_year + 1):
        for suffix in suffixes:
            period = f"{year}{suffix}"
            year_, month_, day_ = split_period(period)
            if date(year_, month_, day_) > as_of:
                continue
            if not is_available(period, as_of):
                continue
            out.append(period)
    return out
