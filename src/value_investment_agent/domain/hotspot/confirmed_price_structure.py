"""Confirmed price structure over the existing completed OHLCV contract."""
from decimal import Decimal

from .price_action_plan import calculate_price_levels

RULE_VERSION = "hotspot-confirmed-structure-v1"
SWING_SIDE_BARS = 2
RETEST_LOOKBACK = 10


def conditional_action_rules(behavior: dict, primary: dict) -> dict:
    """Describe existing observations as conditional reviews, never permissions."""
    def condition(intent, price, observed, rule, holding):
        return dict(intent=intent, price=price, observed=observed, rule=rule,
                    requires_existing_holding=holding, status="CONDITIONAL_REVIEW_ONLY",
                    formal_eligibility=False, personal_permission=False, action="no_order")

    recovery = behavior["pullback_recovery"]
    return {
        "OPEN": condition("OPEN", primary["entry_trigger_price"], primary["breakout_observed"],
            "完整60分钟收盘价严格高于前五根最高价，且成交量至少为前五根均量的1.2倍；"
            "仅在无持仓且价值、事件、风险及验证门禁全部通过后，进入人工开仓复核。", False),
        "ADD": condition("ADD", recovery["evidence"]["level"] if recovery["observed"] else None,
            recovery["observed"],
            "已有持仓时，按既有10根回看规则观察突破后缩量回踩：中间收盘不低于突破位、"
            "触及突破位的量小于突破量，随后完整60分钟收盘高于前根最高价及突破位、"
            "量比至少1.2；全部门禁与个人剩余容量通过后，才进入人工加仓复核。", True),
        "REDUCE": condition("REDUCE", None,
            behavior["observation_quality"] in {"UNFAVORABLE_DAILY_TREND", "INSUFFICIENT_UPPER_SPACE"},
            "已有持仓时，若已确认日线高低点同时下移，或既有结构距离风险收益比不高于1，"
            "进入人工减仓风险复核；这是结构警示，不提供减仓价格、数量或个人卖出许可。", True),
        "EXIT": condition("EXIT", primary["invalidation_price"], behavior["structural_invalidation"],
            "已有持仓时，完整60分钟收盘价严格低于前五根最低价，进入结构失效与人工退出复核；"
            "仍须核查T+1、停牌、涨跌停、成本及个人持仓，不是自动止损订单。", True),
    }


def confirmed_swings(bars: list[dict], *, period: str) -> list[dict]:
    calculate_price_levels(bars, period=period)
    swings = []
    for index in range(SWING_SIDE_BARS, len(bars) - SWING_SIDE_BARS):
        row = bars[index]
        neighbours = bars[index - SWING_SIDE_BARS:index] + bars[index + 1:index + SWING_SIDE_BARS + 1]
        for kind, field, predicate in (("HIGH", "high", lambda a, b: a > b),
                                       ("LOW", "low", lambda a, b: a < b)):
            price = Decimal(row[field])
            if all(predicate(price, Decimal(other[field])) for other in neighbours):
                swings.append(dict(kind=kind, price=str(price), pivot_at=row["time"],
                                   known_at=bars[index + SWING_SIDE_BARS]["time"]))
    return swings


def analyze_price_behavior(bars: dict[str, list[dict]]) -> dict:
    """No unconfirmed swing or subsequent-session trade is inferred."""
    levels = {period: calculate_price_levels(bars[period], period=period)
              for period in ("daily", "60m", "15m")}
    swings = confirmed_swings(bars["daily"], period="daily")
    highs = [point for point in swings if point["kind"] == "HIGH"]
    lows = [point for point in swings if point["kind"] == "LOW"]
    higher_high = len(highs) >= 2 and Decimal(highs[-1]["price"]) > Decimal(highs[-2]["price"])
    higher_low = len(lows) >= 2 and Decimal(lows[-1]["price"]) > Decimal(lows[-2]["price"])
    lower_high = len(highs) >= 2 and Decimal(highs[-1]["price"]) < Decimal(highs[-2]["price"])
    lower_low = len(lows) >= 2 and Decimal(lows[-1]["price"]) < Decimal(lows[-2]["price"])
    trend = ("UNKNOWN" if len(highs) < 2 or len(lows) < 2 else
             "UPTREND" if higher_high and higher_low else
             "DOWNTREND" if lower_high and lower_low else "RANGE")
    rows = bars["60m"]
    previous = calculate_price_levels(rows[:-1], period="60m") if len(rows) >= 7 else None
    last = rows[-1]
    confirmed_breakout = bool(previous and previous["breakout_observed"]
                             and Decimal(last["close"]) > Decimal(previous["entry_trigger_price"]))
    retest = None
    for index in range(max(5, len(rows) - RETEST_LOOKBACK - 1), len(rows) - 2):
        event = calculate_price_levels(rows[:index + 1], period="60m")
        if not event["breakout_observed"]:
            continue
        level = Decimal(event["entry_trigger_price"])
        following = rows[index + 1:-1]
        held = all(Decimal(row["close"]) >= level for row in following)
        touches = [row for row in following if Decimal(row["low"]) <= level]
        contracted = bool(touches) and all(Decimal(row["volume"]) < Decimal(rows[index]["volume"]) for row in touches)
        recovers = (Decimal(last["close"]) > Decimal(rows[-2]["high"])
                    and Decimal(last["close"]) > level
                    and Decimal(levels["60m"]["volume_ratio"]) >= Decimal("1.2"))
        if held and contracted and recovers:
            retest = dict(breakout_at=rows[index]["time"], level=str(level),
                          confirmed_at=last["time"], contracted_touch_count=len(touches))
    entry = Decimal(levels["60m"]["entry_trigger_price"])
    protection = Decimal(levels["60m"]["invalidation_price"])
    targets = [point for point in highs[-2:] if Decimal(point["price"]) > entry]
    resistance = min(targets, key=lambda point: Decimal(point["price"])) if targets else None
    ratio = ((Decimal(resistance["price"]) - entry) / (entry - protection)
             if resistance and entry > protection else None)
    return dict(rule_version=RULE_VERSION, action="no_order", formal_eligibility=False,
                daily_trend=trend, confirmed_swings=swings[-12:],
                higher_high=higher_high, higher_low=higher_low,
                lower_high=lower_high, lower_low=lower_low,
                confirmed_support=lows[-1] if lows else None,
                confirmed_resistance=highs[-1] if highs else None,
                potential_reversal=(trend == "DOWNTREND" and bool(highs)
                                    and Decimal(bars["daily"][-1]["close"]) > Decimal(highs[-1]["price"])),
                breakout=dict(observed=levels["60m"]["breakout_observed"],
                              confirmed_on_next_completed_bar=confirmed_breakout,
                              confirmation_level=previous["entry_trigger_price"] if confirmed_breakout else None,
                              breakout_at=rows[-2]["time"] if confirmed_breakout else None,
                              confirmed_at=last["time"] if confirmed_breakout else None,
                              level=levels["60m"]["entry_trigger_price"]),
                pullback_recovery=dict(observed=retest is not None, evidence=retest),
                range_breakout=dict(observed=trend == "RANGE" and levels["60m"]["breakout_observed"]),
                auxiliary_15m=dict(observed=levels["15m"]["breakout_observed"], scope="AUXILIARY_OBSERVATION_ONLY"),
                volume_ratio=levels["60m"]["volume_ratio"],
                structural_protection_price=str(protection),
                structural_invalidation=Decimal(last["close"]) < protection,
                nearest_confirmed_upper_resistance=resistance,
                risk_reward_ratio=str(ratio) if ratio is not None else None,
                risk_reward_scope="STRUCTURAL_DISTANCE_BEFORE_COST_NOT_EXPECTED_RETURN",
                risk_reward_blocker=None if ratio is not None else "NO_CONFIRMED_TARGET_ABOVE_ENTRY_OR_INVALID_PRICE_RISK",
                observation_quality=("UNFAVORABLE_DAILY_TREND" if trend == "DOWNTREND" else
                                     "INSUFFICIENT_UPPER_SPACE" if ratio is not None and ratio <= 1 else
                                     "UNKNOWN" if trend == "UNKNOWN" or ratio is None else "RESEARCH_ONLY"),
                observed_at=last["time"], first_action_session="SUBSEQUENT_EXCHANGE_SESSION",
                execution_checks=["GAP", "PRICE_LIMIT", "SUSPENSION", "UNFILLED", "SLIPPAGE", "T_PLUS_ONE"],
                blockers=["RULE_VALIDATION_NOT_ADMITTED", "HISTORICAL_CLASSIFICATION_PIT_NOT_PROVEN",
                          "MINUTE_SINGLE_SOURCE", "PERSONAL_RISK_AND_EVENT_REVIEW_REQUIRED"])
