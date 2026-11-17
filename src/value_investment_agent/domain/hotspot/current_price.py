"""Completed-session integrity and observation-only current price projection."""

from datetime import datetime, time
from decimal import Decimal

from .price_action_plan import calculate_price_levels

SESSION_TIMES = {
    "60m": ("10:30:00", "11:30:00", "14:00:00", "15:00:00"),
    "15m": tuple(f"{hour:02}:{minute:02}:00" for hour, minutes in
                 ((9, (45,)), (10, (0, 15, 30, 45)), (11, (0, 15, 30)),
                  (13, (15, 30, 45)), (14, (0, 15, 30, 45)), (15, (0,))) for minute in minutes)
}
CURRENT_BLOCKERS = ["INTRADAY_SINGLE_PROVIDER", "VALUE_GATE_NOT_PROVEN",
                    "EVENT_AND_RISK_GATES_NOT_PROVEN", "PIT_OOS_COST_SHADOW_NOT_PROVEN",
                    "CORPORATE_ACTION_REVIEW_NOT_PROVEN"]
SIGNAL_STATES = frozenset({"WATCH", "TRIGGER_PENDING", "TRIGGER_OBSERVED",
                           "TRIGGER_REJECTED", "STALE", "BLOCKED", "ACTION_ELIGIBLE"})


def completed_session_bars(bars: list[dict], *, period: str) -> list[dict]:
    """Discard only a leading partial window; reject any later incomplete day."""
    days = {}
    calculate_price_levels(bars, period=period)
    for bar in bars:
        stamp = datetime.fromisoformat(bar["time"])
        if stamp.tzinfo is not None or stamp.time() < time(9, 30):
            raise ValueError("Invalid session timestamp")
        days.setdefault(stamp.date(), []).append(bar)
    result = []
    for index, rows in enumerate(days.values()):
        clocks = tuple(row["time"][11:] for row in rows)
        if clocks != SESSION_TIMES[period]:
            if index == 0 and clocks == SESSION_TIMES[period][-len(clocks):]:
                continue
            raise ValueError(f"Incomplete {period} session")
        result.extend(rows)
    if not result:
        raise ValueError("No complete sessions")
    return result


def aggregate_sessions(bars: list[dict]) -> list[dict]:
    days = {}
    for bar in bars:
        days.setdefault(bar["time"][:10], []).append(bar)
    return [dict(time=day, open=rows[0]["open"], close=rows[-1]["close"],
                 high=str(max(Decimal(r["high"]) for r in rows)),
                 low=str(min(Decimal(r["low"]) for r in rows)),
                 volume=str(sum(Decimal(r["volume"]) for r in rows)),
                 amount=str(sum(Decimal(r["amount"]) for r in rows)))
            for day, rows in days.items()]


def current_signal(levels: dict) -> tuple[str, str]:
    primary = levels["60m"]
    if primary["breakout_observed"]:
        return "TRIGGER_OBSERVED", "60分钟完整收盘价与成交量满足突破观察条件；不据此认定多周期趋势，独立门禁未完成，不能执行交易。"
    close = Decimal(primary["reference_close"])
    if close < Decimal(primary["invalidation_price"]):
        return "TRIGGER_REJECTED", "60分钟完整收盘价跌破前五根最低价，触发条件失效，需要重新研究。"
    if close > Decimal(primary["entry_trigger_price"]):
        return "TRIGGER_PENDING", "60分钟完整收盘价超过前五根最高价，但成交量未达到1.2倍，等待后续完整交易时段确认。"
    return "WATCH", "60分钟完整收盘价尚未满足突破条件，继续观察；其他周期信号不替代主周期。"
