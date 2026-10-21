"""Deterministic completed-bar price levels, never an order or admission."""

from decimal import Decimal, InvalidOperation

RULE_VERSION = "hotspot-prior-five-completed-bars-v1"


def _positive(value: object, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError) as error:
        raise ValueError(f"Invalid {field}") from error
    if not number.is_finite() or number <= 0:
        raise ValueError(f"Invalid {field}")
    return number


def calculate_price_levels(bars: list[dict], *, period: str) -> dict:
    """Latest completed close vs the previous five completed bars.

    The trigger is a strict close above the prior high with volume at least
    1.2x the prior-five mean. The prior low is a structural invalidation
    reference, not an executable stop order. No target is inferred.
    """
    if period not in {"daily", "60m", "15m"}:
        raise ValueError("Unsupported period")
    if len(bars) < 6:
        raise ValueError("Six completed bars required")
    times = [str(bar["time"]) for bar in bars]
    if times != sorted(set(times)):
        raise ValueError("Bar times must be unique and ordered")
    for bar in bars:
        opening = _positive(bar["open"], "open")
        high = _positive(bar["high"], "high")
        low = _positive(bar["low"], "low")
        close = _positive(bar["close"], "close")
        _positive(bar["volume"], "volume")
        if low > min(opening, close) or high < max(opening, close):
            raise ValueError("Invalid OHLC bounds")
    prior = bars[-6:-1]
    latest = bars[-1]
    trigger = max(_positive(bar["high"], "high") for bar in prior)
    invalidation = min(_positive(bar["low"], "low") for bar in prior)
    close = _positive(latest["close"], "close")
    mean_volume = sum(_positive(bar["volume"], "volume") for bar in prior) / 5
    volume_ratio = _positive(latest["volume"], "volume") / mean_volume
    return {
        "period": period,
        "rule_version": RULE_VERSION,
        "window": 5,
        "bar_count": len(bars),
        "first_bar": times[0],
        "last_bar": times[-1],
        "reference_close": str(close),
        "entry_trigger_price": str(trigger),
        "entry_confirmation_rule": "completed_close > prior_5_high AND volume >= 1.2 * prior_5_mean_volume",
        "invalidation_price": str(invalidation),
        "invalidation_rule": "subsequent completed close < prior_5_low; research review required",
        "volume_ratio": str(volume_ratio),
        "breakout_observed": close > trigger and volume_ratio >= Decimal("1.2"),
        "risk_reward_ratio": None,
        "target_price": None,
        "action": "no_order",
    }
