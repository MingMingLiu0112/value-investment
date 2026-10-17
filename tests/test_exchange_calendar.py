from datetime import date

import pytest

from value_investment_agent.domain.execution.exchange_calendar import (
    ExchangeCalendarCoverageError,
    SCHEDULE_VERSION,
    is_exchange_session,
    next_exchange_session,
    validate_buy_settlement,
)


def test_weekend_rolls_to_monday_without_date_arithmetic_shortcuts():
    assert next_exchange_session("SSE", date(2026, 10, 16)) == date(2026, 10, 19)
    assert next_exchange_session("SZSE", date(2026, 10, 16)) == date(2026, 10, 19)


def test_national_day_closure_uses_the_official_exchange_schedule():
    assert next_exchange_session("SSE", date(2026, 9, 30)) == date(2026, 10, 8)
    assert not is_exchange_session("SSE", date(2026, 10, 1))
    assert not is_exchange_session("SSE", date(2026, 10, 7))
    assert is_exchange_session("SSE", date(2026, 10, 8))


@pytest.mark.parametrize(
    "venue, trade_date, next_sell_session, message",
    [
        ("SSE", date(2026, 10, 10), date(2026, 10, 12), "trade date is not"),
        ("SSE", date(2026, 9, 30), date(2026, 10, 1), "next covered exchange session"),
        ("SSE", date(2026, 10, 12), date(2026, 10, 14), "next covered exchange session"),
        ("SSE", date(2026, 10, 12), None, "explicit later sell session"),
    ],
)
def test_buy_settlement_rejects_weekend_holiday_or_non_t_plus_one(
    venue, trade_date, next_sell_session, message
):
    with pytest.raises(ValueError, match=message):
        validate_buy_settlement(venue, trade_date, next_sell_session)


def test_buy_settlement_accepts_exact_next_exchange_session():
    assert validate_buy_settlement(
        "SSE", date(2026, 10, 12), date(2026, 10, 13)
    ) == date(2026, 10, 13)


@pytest.mark.parametrize(
    "venue, day",
    [("BSE", date(2026, 10, 12)), ("SSE", date(2027, 1, 4))],
)
def test_uncovered_exchange_or_year_fails_closed(venue, day):
    with pytest.raises(ExchangeCalendarCoverageError, match=SCHEDULE_VERSION):
        is_exchange_session(venue, day)

