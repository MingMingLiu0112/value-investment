"""Deterministic execution of frozen orders; no signal fitting or admission."""
from collections import Counter
from datetime import datetime, time as clock_time
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from ..execution.exchange_calendar import is_exchange_session

CHINA = ZoneInfo("Asia/Shanghai")


def number(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Invalid execution number") from error
    if not result.is_finite() or result < 0:
        raise ValueError("Finite nonnegative execution number required")
    return result


def stamp(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("Execution timestamp requires timezone")
    return result


def validate_replay_order_quantity(symbol, quantity, side, execution_at):
    """Limit-order mechanics only; never establish board permission or tradability."""
    if type(quantity) is not int or quantity <= 0 or side not in ('BUY', 'SELL'):
        raise ValueError('Positive integer BUY/SELL quantity required')
    if symbol.startswith('688'):
        if stamp(execution_at).astimezone(CHINA).date().isoformat() < '2026-07-06':
            raise ValueError('STAR quantity rule before reviewed effective window is unsupported')
        if quantity > 100000 or (side == 'BUY' and quantity < 200):
            raise ValueError('STAR limit quantity must be 200..100000 for BUY')
        # Sub-200 SELL is allowed here only for the existing full-exit matcher,
        # which separately requires the entire remaining inventory to be sold.
    elif quantity % 100:
        raise ValueError('Round-lot BUY/SELL required')


def simulate_fold(protocol, inputs, fold, *, cost_multiplier=Decimal(1)):
    """One isolated long-only account, full exits, next-bar bounded fills.

    Orders expire at their specified bar; rejected exits leave inventory intact.
    Close marks include open inventory, whereas trade returns require an exit.
    """
    start, end = stamp(fold["test_start"]), stamp(fold["test_end"])
    fees = protocol["costs"]
    commission, minimum, tax, slip = (number(fees[k]) for k in
        ("commission_rate", "minimum_commission_cny", "sell_tax_rate", "slippage_bps"))
    if max(commission, tax) >= 1 or slip >= 10000:
        raise ValueError("Invalid execution rates")
    cash = initial = number(protocol["initial_cash_cny"])
    if initial <= 0:
        raise ValueError("Positive initial cash required")
    positions, marks, fills, rejected, trades, curve = {}, {}, [], [], [], []
    orders = {}
    ids = set()
    for order in inputs["orders"]:
        if order["id"] in ids:
            raise ValueError("Duplicate order identity")
        ids.add(order["id"])
        decision, execution = stamp(order["decision_at"]), stamp(order["execute_at"])
        if stamp(order["available_at"]) > decision or decision >= execution:
            raise ValueError("Order availability must precede next-bar execution")
        if order["fold"] != fold["id"]:
            continue
        if not start <= decision < execution <= end:
            raise ValueError("Order crosses OOS fold cutoff")
        validate_replay_order_quantity(order['symbol'], order['quantity'], order['side'], order['execute_at'])
        orders.setdefault((execution, order["symbol"]), []).append(order)
    seen = set()
    for bar in sorted(inputs["bars"], key=lambda row: (stamp(row["time"]), row["symbol"])):
        time, symbol = stamp(bar["time"]), bar["symbol"]
        key = (time, symbol)
        if key in seen:
            raise ValueError("Duplicate execution bar")
        seen.add(key)
        if not start <= time <= end:
            continue
        local = time.astimezone(CHINA)
        if (not is_exchange_session("SSE", local.date()) or not (
                clock_time(9, 30) <= local.time() <= clock_time(11, 30)
                or clock_time(13) <= local.time() <= clock_time(15))):
            raise ValueError("Execution bar outside exchange session")
        if not stamp(fees["effective_start"]) <= time <= stamp(fees["effective_end"]):
            raise ValueError("Execution outside dated cost validity")
        opening, close = number(bar["open"]), number(bar["close"])
        lower, upper = number(bar["limit_down"]), number(bar["limit_up"])
        if not 0 < lower < upper or not lower <= opening <= upper or not lower <= close <= upper:
            raise ValueError("Invalid dated price bounds")
        marks[symbol] = close
        consumed = Decimal(0)
        for order in orders.pop(key, []):
            qty, side = order["quantity"], order["side"]
            sign = Decimal(1) if side == "BUY" else Decimal(-1)
            price = (opening * (1 + sign * slip * cost_multiplier / 10000)).quantize(
                Decimal("0.01"), rounding=ROUND_CEILING if side == "BUY" else ROUND_FLOOR)
            gross = price * qty
            charge = (max(minimum, gross * commission) * cost_multiplier).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
            charge += (gross * number(fees["transfer_fee_rate"]) * cost_multiplier).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
            if side == "SELL":
                charge += (gross * tax * cost_multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            holding = positions.get(symbol)
            reason = None
            if type(bar["suspended"]) is not bool:
                raise ValueError("Explicit suspension state required")
            if bar["suspended"]:
                reason = "SUSPENDED"
            elif not lower < opening < upper or not lower < price < upper:
                reason = "PRICE_LIMIT"
            elif gross + consumed > number(bar["liquidity_cny"]) or gross > number(order["liquidity_budget_cny"]):
                reason = "LIQUIDITY"
            elif (side == "BUY" and price > number(order["limit_price"])) or (
                    side == "SELL" and price < number(order["limit_price"])):
                reason = "ORDER_LIMIT"
            elif side == "BUY" and holding:
                reason = "POSITION_ALREADY_OPEN"
            elif side == "BUY" and gross + charge > cash:
                reason = "CASH"
            elif side == "SELL" and (not holding or holding["quantity"] != qty):
                reason = "FULL_EXIT_INVENTORY_REQUIRED"
            elif side == "SELL" and time.astimezone(CHINA).date() <= holding["date"]:
                reason = "T_PLUS_ONE"
            if reason:
                rejected.append(dict(order_id=order["id"], reason=reason))
                continue
            consumed += gross
            slippage = abs(price - opening) * qty
            fills.append(dict(order_id=order["id"], time=bar["time"], symbol=symbol,
                side=side, price=str(price), quantity=qty, fees_cny=str(charge),
                slippage_cny=str(slippage)))
            if side == "BUY":
                cash -= gross + charge
                positions[symbol] = dict(quantity=qty, date=time.astimezone(CHINA).date(), basis=gross + charge)
            else:
                cash += gross - charge
                pnl = gross - charge - holding["basis"]
                trades.append(dict(symbol=symbol, exit_at=bar["time"], pnl_cny=str(pnl),
                    net_return=str(pnl / holding["basis"])))
                del positions[symbol]
        equity = cash + sum(p["quantity"] * marks[s] for s, p in positions.items())
        # Coalesce simultaneous marks so symbol ordering cannot create drawdown.
        point = dict(time=bar["time"], equity_cny=str(equity))
        if curve and stamp(curve[-1]["time"]) == time:
            curve[-1] = point
        else:
            curve.append(point)
    rejected.extend(dict(order_id=o["id"], reason="NO_EXECUTION_BAR")
                    for batch in orders.values() for o in batch)
    peak, drawdown = initial, Decimal(0)
    for point in curve:
        equity = Decimal(point["equity_cny"])
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    returns = [Decimal(t["net_return"]) for t in trades]
    wins, losses = [x for x in returns if x > 0], [x for x in returns if x < 0]
    payoff = ((sum(wins) / len(wins)) / abs(sum(losses) / len(losses))) if wins and losses else None
    return dict(fold=fold["id"], fills=fills, rejected_orders=rejected, trades=trades,
        trade_count=len(trades), unfilled_count=len(rejected),
        filled_order_count=len(fills),
        unfilled_rate=str(Decimal(len(rejected)) / (len(fills) + len(rejected))) if fills or rejected else None,
        rejection_counts=dict(Counter(r["reason"] for r in rejected)),
        win_rate=str(Decimal(len(wins)) / len(trades)) if trades else None,
        payoff_ratio=str(payoff) if payoff is not None else None,
        net_return_distribution=[str(x) for x in returns], maximum_drawdown=str(drawdown),
        drawdown_basis="BAR_CLOSE_MARK_TO_MARKET_INCLUDING_OPEN_INVENTORY",
        equity_curve=curve, ending_cash_cny=str(cash),
        ending_equity_cny=curve[-1]["equity_cny"] if curve else str(initial),
        right_censored_positions=len(positions),
        total_fees_cny=str(sum((Decimal(f["fees_cny"]) for f in fills), Decimal(0))),
        total_slippage_cny=str(sum((Decimal(f["slippage_cny"]) for f in fills), Decimal(0))))
