"""Single-event cash-coordinate arithmetic, not strategy or market admission."""
from datetime import date
from decimal import Decimal, InvalidOperation


def _positive(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("Finite positive price/entitlement required") from error
    if not number.is_finite() or number <= 0:
        raise ValueError("Finite positive price/entitlement required")
    return number


def map_cash_price_coordinates(*, original_protection, current_price, cash_per_share,
        original_basis_date: date, current_basis_date: date, ex_date: date) -> dict:
    """Assume one verified pure-cash event only; all other actions remain unknown.

    Subtract gross cash from the old level, or add it to the new price. Neither
    is an exchange rounded quote, total return, personal stop or a fill promise.
    Dates denote ex-basis observations, not intraday entitlement ownership.
    """
    if (any(type(day) is not date for day in (original_basis_date, current_basis_date, ex_date))
            or original_basis_date > current_basis_date):
        raise ValueError("Ordered explicit price-basis dates required")
    protection, current, cash = map(_positive, (original_protection, current_price, cash_per_share))
    crossed = original_basis_date < ex_date <= current_basis_date
    adjustment = cash if crossed else Decimal(0)
    mapped = protection - adjustment
    if mapped <= 0:
        raise ValueError("Cash-only mapping would produce a nonpositive protection level")
    return dict(schema_version="hotspot-single-cash-price-mapping-v1",
        mapping_status="CONDITIONAL_SINGLE_EVENT_MAPPING" if crossed else "EVENT_NOT_CROSSED",
        original_basis_date=original_basis_date.isoformat(), current_basis_date=current_basis_date.isoformat(),
        ex_date=ex_date.isoformat(), event_crossed=crossed, gross_cash_per_share=str(cash),
        original_protection_price=str(protection), original_current_price=str(current),
        event_only_protection_on_current_basis=str(mapped),
        event_only_current_on_original_basis=str(current + adjustment),
        raw_distance_to_original_protection=str(current - protection),
        event_only_distance_to_protection=str(current - mapped),
        formula="P_after=P_before-D; Q_before=Q_after+D" if crossed else "IDENTITY_NO_EVENT_CROSSING",
        rounding="NONE_DECIMAL_COORDINATES_NOT_EXCHANGE_TICK_PRICE",
        price_input_scope="REFERENCE_ONLY_NOT_VERIFIED_QUOTES_OR_OWNED_ENTRY",
        other_actions_assumed_absent_for_calculation_only=True,
        complete_window_coverage=False, same_basis_confirmed=False,
        scope="SINGLE_EVENT_CONDITIONAL_ARITHMETIC_NOT_ADMITTED_PROTECTION",
        tax_or_total_return_calculated=False, formal_eligibility=False, action="no_order")
