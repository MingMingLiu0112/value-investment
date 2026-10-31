"""Rule-derived retrospective intents using the existing execution simulator.

The exit/size/latency convention is an explicit research experiment, not a
change to the frozen observation rule or an admitted strategy.
"""
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from .current_price import completed_session_bars
from .price_action_plan import RULE_VERSION, calculate_price_levels
from .quantitative_validation import CHINA, number, simulate_fold, stamp, validate_replay_order_quantity

EXPERIMENT_VERSION = "breakout-next-bar-fixed-lot-close-invalidation-five-session-v1"
DEFAULT_INITIAL_CASH_CNY = 100_000
START_CLOCK = {"10:30:00": "09:30:00", "11:30:00": "10:30:00",
               "14:00:00": "13:00:00", "15:00:00": "14:00:00"}


def _local(value):
    result = datetime.fromisoformat(value)
    return result.replace(tzinfo=CHINA) if result.tzinfo is None else result.astimezone(CHINA)


def _execution_bar(symbol, row, daily, states, mode, participation):
    label = _local(row["time"])
    start = _local(row["time"][:10] + " " + START_CLOCK[row["time"][11:]])
    state = states.get(row["time"])
    issue = None
    assumption = False
    if state is not None:
        if stamp(state["available_at"]) > start:
            raise ValueError("Stock status not known before execution bar")
        if type(state["suspended"]) is not bool:
            raise ValueError("Explicit suspension state required")
        lower, upper = number(state["limit_down"]), number(state["limit_up"])
        suspended = state["suspended"]
    else:
        prior = [r for r in daily if r["time"] < row["time"][:10]]
        assumption = True
        if mode == "STRICT" or not prior:
            issue = "MISSING_DATED_STOCK_STATUS"
        # These bounds permit mark-to-market only in STRICT mode: every intent
        # at an unverified bar is rejected before reaching the matching engine.
        rate = Decimal("0.20") if symbol.startswith(("30", "68")) else Decimal("0.10")
        previous = number(prior[-1]["close"]) if prior else number(row["open"])
        lower = (previous * (1 - rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        upper = (previous * (1 + rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        suspended = False
    if not 0 < lower < upper:
        raise ValueError("Invalid stock price limits")
    if not lower <= number(row["open"]) <= upper or not lower <= number(row["close"]) <= upper:
        if state is not None:
            raise ValueError("Source price outside verified price limits")
        issue = "ASSUMED_LIMIT_CONFLICT_OR_CORPORATE_ACTION"
    # Out-of-bound or missing states cannot generate fills. Keep their actual
    # close marks using explicit non-trading bounds instead of dropping bars.
    mark_lower = min(lower, number(row["low"]) / 2)
    mark_upper = max(upper, number(row["high"]) * 2)
    amount = number(row["amount"])
    return dict(symbol=symbol, time=label.isoformat(), open=row["open"], close=row["close"],
        limit_down=str(mark_lower if issue else lower), limit_up=str(mark_upper if issue else upper),
        suspended=suspended, liquidity_cny=str(amount * participation)), {
            "bar_label": row["time"], "open_at": start.isoformat(),
            "hypothetical_fill_at": (start + timedelta(seconds=1)).isoformat(),
            "state_assumed": assumption, "rejection": issue,
            "liquidity_basis": "EX_POST_BAR_TURNOVER_CAPACITY_NOT_KNOWN_AT_DECISION",
        }


def _execution_rejection(intention, row, bar, observation, costs, cost_multiplier):
    reason = observation['rejection']
    if (not reason and intention['side'] == 'BUY'
            and number(row['open']) < number(intention['entry_invalidation'])):
        reason = 'GAP_BELOW_ENTRY_INVALIDATION'
    slip = number(costs['slippage_bps']) * number(cost_multiplier) / 10000
    hypothetical = (number(row['open']) * (1 + slip if intention['side'] == 'BUY' else 1 - slip)).quantize(
        Decimal('0.01'), rounding=ROUND_CEILING if intention['side'] == 'BUY' else ROUND_FLOOR)
    inside = number(bar['limit_down']) < number(row['open']) < number(bar['limit_up'])
    if not reason and inside and not number(row['low']) <= hypothetical <= number(row['high']):
        reason = 'SLIPPAGE_OUTSIDE_OBSERVED_BAR'
    return reason


def replay_strategy_execution(*, symbol, bars_by_period, spec, costs,
                              stock_states=None, mode="STRICT", initial_cash=DEFAULT_INITIAL_CASH_CNY,
                              quantity=100, participation="0.01", cost_multiplier="1"):
    """Generate intentions online from prefixes; supplied orders are not accepted.

    Entry: frozen 60m breakout, no pyramiding, one next-bar attempt at no more
    than signal close. Exit: frozen entry invalidation on completed close, or
    fifth subsequent observed session close; retry rejected exits next bar.
    Every prefix fill and final metric is calculated by simulate_fold.
    """
    if mode not in {"STRICT", "ASSUMED_REGULAR_TRADING"}:
        raise ValueError("Explicit stock-state mode required")
    if not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isdigit():
        raise ValueError("Invalid security identity")
    if not symbol.startswith(("0", "30", "60", "688")):
        raise ValueError("Security board lot and limit conventions not supported")
    if not symbol.startswith('688') and (type(quantity) is not int or quantity <= 0 or quantity % 100):
        raise ValueError("Positive round-lot quantity required")
    ratio = number(participation)
    if not 0 < ratio <= 1 or number(initial_cash) <= 0:
        raise ValueError("Invalid cash or participation")
    if number(cost_multiplier) > 10:
        raise ValueError("Unsupported cost sensitivity")
    if number(costs["slippage_bps"]) * number(cost_multiplier) >= 10000:
        raise ValueError("Scaled slippage must leave a positive execution price")
    # Frozen specification validation, including unchanged five-session horizon.
    from .event_replay import validate_spec
    validate_spec(spec)
    if symbol.startswith('688'):
        validate_replay_order_quantity(symbol, quantity, 'BUY', spec['start_date'] + 'T09:30:00+08:00')
    rows = completed_session_bars(bars_by_period["60m"], period="60m")
    daily = bars_by_period["daily"]
    calculate_price_levels(daily, period="daily")
    if [r["time"] for r in daily] != sorted({r["time"] for r in daily}):
        raise ValueError("Unique ordered daily bars required")
    if any(len(r["time"]) != 10 for r in daily):
        raise ValueError("Daily bar labels must be dates")
    states = stock_states or {}
    unknown = set(states) - {r["time"] for r in rows}
    if unknown:
        raise ValueError("Stock status references unknown execution bars")
    partitions = [("development", spec["start_date"], spec["development_end"]),
                  ("validation", spec["validation_start"], spec["end_date"])]
    results = []
    for name, start_day, end_day in partitions:
        fold = dict(id=name, test_start=start_day + "T09:30:00+08:00",
                    test_end=end_day + "T15:00:00+08:00")
        protocol = dict(initial_cash_cny=str(initial_cash), costs=costs)
        execution, orders, intentions, rejected, observations = [], [], [], [], []
        current, pending, exit_requested = None, None, False
        signal_count, censored, suppressed = 0, 0, 0
        for index, row in enumerate(rows):
            day = row["time"][:10]
            if not start_day <= day <= end_day:
                continue
            bar, observation = _execution_bar(symbol, row, daily, states, mode, ratio)
            execution.append(bar)
            observations.append(observation)
            if pending:
                intention = dict(pending, execute_at=bar["time"],
                    actual_execution_at=observation["hypothetical_fill_at"],
                    execution_bar_label=row["time"])
                if stamp(intention["actual_execution_at"]) <= stamp(intention["decision_at"]):
                    raise ValueError("Execution cannot precede completed signal")
                intentions.append(intention)
                reason = _execution_rejection(intention, row, bar, observation, costs, cost_multiplier)
                if reason:
                    rejected.append(dict(order_id=intention["id"], reason=reason))
                else:
                    order = {key: intention[key] for key in ("id", "symbol", "side", "quantity",
                        "fold", "decision_at", "available_at", "execute_at", "limit_price",
                        "liquidity_budget_cny")}
                    orders.append(order)
                    last_metrics = simulate_fold(protocol, dict(orders=orders, bars=execution), fold,
                                                 cost_multiplier=number(cost_multiplier))
                    fill = next((f for f in last_metrics["fills"] if f["order_id"] == order["id"]), None)
                    if fill:
                        if fill["side"] == "BUY":
                            current = dict(invalidation=intention["entry_invalidation"],
                                entry_day=day, entry_signal=intention["decision_at"], days=[])
                        else:
                            current, exit_requested = None, False
                pending = None
            # Only the now-completed bar can change the next execution intention.
            if index < 5:
                continue
            levels = calculate_price_levels(rows[index - 5:index + 1], period="60m")
            triggered = levels["breakout_observed"]
            signal_count += int(triggered)
            if current:
                if day > current["entry_day"] and day not in current["days"]:
                    current["days"].append(day)
                invalid = number(row["close"]) < number(current["invalidation"])
                horizon = len(current["days"]) >= 5 and row["time"][11:] == "15:00:00"
                exit_requested = exit_requested or invalid or horizon
                side = "SELL" if exit_requested else None
                reason = "ENTRY_CLOSE_INVALIDATION" if invalid else "HORIZON_OR_RETRY"
                suppressed += int(triggered)
            else:
                side = "BUY" if triggered else None
                reason = "FROZEN_COMPLETED_BAR_BREAKOUT"
            if side:
                decision = _local(row["time"]).isoformat()
                pending = dict(id=f"{symbol}-{name}-{index}-{side}", fold=name,
                    symbol=symbol, side=side, quantity=quantity, decision_at=decision,
                    available_at=decision, availability_scope="HYPOTHETICAL_BAR_CLOSE_NOT_ARCHIVAL_PIT",
                    limit_price=levels["reference_close"] if side == "BUY" else "0.01",
                    liquidity_budget_cny=str(number(initial_cash)),
                    entry_invalidation=levels["invalidation_price"] if side == "BUY" else current["invalidation"],
                    reason=reason)
        if pending:
            censored += 1
        metrics = simulate_fold(protocol, dict(orders=orders, bars=execution), fold,
                                cost_multiplier=number(cost_multiplier))
        all_rejected = metrics["rejected_orders"] + rejected
        metrics.update(rejected_orders=all_rejected,
            rejection_counts=dict(Counter(r["reason"] for r in all_rejected)),
            unfilled_count=len(all_rejected),
            unfilled_rate=str(Decimal(len(all_rejected)) / len(intentions)) if intentions else None,
            signal_event_count=signal_count, position_suppressed_signals=suppressed,
            right_censored_intentions=censored, pending_intention=pending,
            generated_intentions=intentions, simulator_inputs=dict(orders=orders, bars=execution),
            execution_observations=observations,
            net_return=str(number(metrics["ending_equity_cny"]) / number(initial_cash) - 1))
        results.append(metrics)
    result = dict(experiment_version=EXPERIMENT_VERSION, rule_version=RULE_VERSION,
        symbol=symbol, mode=mode, folds=results,
        trade_count=sum(r["trade_count"] for r in results),
        signal_event_count=sum(r["signal_event_count"] for r in results),
        right_censored_positions=sum(r["right_censored_positions"] for r in results),
        right_censored_intentions=sum(r["right_censored_intentions"] for r in results),
        strict_pit_admitted=False, strict_oos_admitted=False, formal_eligibility=False,
        strategy_validation="NOT_PROVEN", performance_claim_allowed=False, action="no_order")
    if symbol.startswith('688'):
        result.update(experiment_version=EXPERIMENT_VERSION + '-star-limit-units-v2',
            quantity_rule_scope='SSE_STAR_LIMIT_ORDERS_REVIEWED_FROM_20260706',
            full_tradability_verified=False,
            remaining_execution_gaps=['DATED_STOCK_STATE_AND_PRICE_LIMITS',
                'CONTINUOUS_AUCTION_PRICE_CAGE_AND_ORDER_BOOK', 'INVESTOR_BOARD_PERMISSION',
                'CORPORATE_ACTION_ODD_BALANCE_NOT_GENERATED'])
    return result


def replay_shared_strategy_execution(*, bars_by_symbol, spec, costs, stock_states_by_symbol=None,
        mode='STRICT', initial_cash=DEFAULT_INITIAL_CASH_CNY, quantity=100, cost_multiplier='1'):
    """Frozen rules with actual simulated shared fills driving each symbol state.

    No source PIT, tradability or real-order claim follows from this experiment.
    Each declared partition resets one common cash account and all positions.
    """
    if not isinstance(bars_by_symbol, dict) or not 1 <= len(bars_by_symbol) <= 10:
        raise ValueError('Bounded one-to-ten security shared replay required')
    symbols = sorted(bars_by_symbol)
    states = stock_states_by_symbol or {}
    if set(states) - set(symbols):
        raise ValueError('Stock states reference an unknown shared security')
    # Reuse the existing input/board/cost/state validation and compiled bars.
    compiled = {symbol: replay_strategy_execution(symbol=symbol,
        bars_by_period=bars_by_symbol[symbol], spec=spec, costs=costs,
        stock_states=states.get(symbol), mode=mode, initial_cash=initial_cash,
        quantity=quantity, cost_multiplier=cost_multiplier) for symbol in symbols}
    rows = {symbol: completed_session_bars(bars_by_symbol[symbol]['60m'], period='60m')
            for symbol in symbols}
    indices = {symbol: {row['time']: i for i, row in enumerate(series)}
               for symbol, series in rows.items()}
    protocol = dict(initial_cash_cny=str(initial_cash), costs=costs)
    results = []
    for name, first, last in [('development', spec['start_date'], spec['development_end']),
                              ('validation', spec['validation_start'], spec['end_date'])]:
        fold = dict(id=name, test_start=first + 'T09:30:00+08:00', test_end=last + 'T15:00:00+08:00')
        parts = {symbol: next(part for part in compiled[symbol]['folds'] if part['fold'] == name)
                 for symbol in symbols}
        timelines = {symbol: [item['bar_label'] for item in part['execution_observations']]
                     for symbol, part in parts.items()}
        timeline = timelines[symbols[0]]
        if not timeline or any(value != timeline for value in timelines.values()):
            raise ValueError('Aligned complete same-pool bar timelines required')
        holdings, pending, exit_requested = {}, {}, {symbol: False for symbol in symbols}
        execution, orders, intentions, rejected, trace = [], [], [], [], []
        signals = suppressed = 0
        for offset, label in enumerate(timeline):
            bars = {symbol: parts[symbol]['simulator_inputs']['bars'][offset] for symbol in symbols}
            observations = {symbol: parts[symbol]['execution_observations'][offset] for symbol in symbols}
            execution.extend(bars.values())
            attempted, new_orders = {}, []
            for symbol in symbols:
                if symbol not in pending:
                    continue
                raw = rows[symbol][indices[symbol][label]]
                observation, bar = observations[symbol], bars[symbol]
                intention = dict(pending[symbol], execute_at=bar['time'],
                    actual_execution_at=observation['hypothetical_fill_at'], execution_bar_label=label)
                if stamp(intention['actual_execution_at']) <= stamp(intention['decision_at']):
                    raise ValueError('Shared execution must follow completed decision')
                intentions.append(intention)
                attempted[intention['id']] = intention
                reason = _execution_rejection(intention, raw, bar, observation, costs, cost_multiplier)
                if reason:
                    rejected.append(dict(order_id=intention['id'], reason=reason))
                else:
                    new_orders.append({key: intention[key] for key in ('id', 'symbol', 'side',
                        'quantity', 'fold', 'decision_at', 'available_at', 'execute_at',
                        'limit_price', 'liquidity_budget_cny')})
            orders.extend(new_orders)
            if new_orders:
                metrics = simulate_fold(protocol, dict(orders=orders, bars=execution), fold,
                                        cost_multiplier=number(cost_multiplier))
                for fill in metrics['fills']:
                    if fill['order_id'] not in attempted:
                        continue
                    intention, symbol = attempted[fill['order_id']], fill['symbol']
                    if fill['side'] == 'BUY':
                        holdings[symbol] = dict(invalidation=intention['entry_invalidation'],
                            entry_day=label[:10], entry_signal=intention['decision_at'], days=[])
                    else:
                        holdings.pop(symbol)
                        exit_requested[symbol] = False
            pending = {}
            for symbol in symbols:
                index = indices[symbol][label]
                raw = rows[symbol][index]
                current = holdings.get(symbol)
                if index < 5:
                    continue
                levels = calculate_price_levels(rows[symbol][index - 5:index + 1], period='60m')
                triggered = levels['breakout_observed']
                signals += int(triggered)
                if current:
                    if label[:10] > current['entry_day'] and label[:10] not in current['days']:
                        current['days'].append(label[:10])
                    invalid = number(raw['close']) < number(current['invalidation'])
                    horizon = len(current['days']) >= 5 and label[11:] == '15:00:00'
                    exit_requested[symbol] = exit_requested[symbol] or invalid or horizon
                    side = 'SELL' if exit_requested[symbol] else None
                    reason = 'ENTRY_CLOSE_INVALIDATION' if invalid else 'HORIZON_OR_RETRY'
                    suppressed += int(triggered)
                else:
                    side, reason = ('BUY' if triggered else None), 'FROZEN_COMPLETED_BAR_BREAKOUT'
                if side:
                    decision = _local(label).isoformat()
                    pending[symbol] = dict(id=f'shared-{name}-{symbol}-{index}-{side}', fold=name,
                        symbol=symbol, side=side, quantity=quantity, decision_at=decision,
                        available_at=decision, availability_scope='HYPOTHETICAL_BAR_CLOSE_NOT_ARCHIVAL_PIT',
                        limit_price=levels['reference_close'] if side == 'BUY' else '0.01',
                        liquidity_budget_cny=str(number(initial_cash)), reason=reason,
                        entry_invalidation=levels['invalidation_price'] if side == 'BUY' else current['invalidation'])
                trace.append(dict(symbol=symbol, completed_at=label,
                    state='EXIT_PENDING' if current and exit_requested[symbol] else 'HELD' if current else 'FLAT',
                    original_protection=current['invalidation'] if current else None,
                    next_intent=side, scope='HYPOTHETICAL_SHARED_FILL_FEEDBACK', action='no_order'))
        metrics = simulate_fold(protocol, dict(orders=orders, bars=execution), fold,
                                cost_multiplier=number(cost_multiplier))
        if metrics['right_censored_positions'] != len(holdings):
            raise ValueError('Shared strategy state differs from filled inventory')
        if signals != sum(part['signal_event_count'] for part in parts.values()):
            raise ValueError('Shared feedback changed frozen raw trigger calculations')
        all_rejected = metrics['rejected_orders'] + rejected
        if len(metrics['fills']) + len(all_rejected) != len(intentions):
            raise ValueError('Shared frozen-rule intentions do not reconcile')
        metrics.update(rejected_orders=all_rejected,
            rejection_counts=dict(Counter(item['reason'] for item in all_rejected)),
            unfilled_count=len(all_rejected),
            unfilled_rate=str(Decimal(len(all_rejected)) / len(intentions)) if intentions else None,
            signal_event_count=signals, position_suppressed_signals=suppressed,
            generated_intentions=intentions, pending_intentions=list(pending.values()),
            right_censored_intentions=len(pending), state_trace=trace,
            simulator_inputs=dict(orders=orders, bars=execution), preflight_rejected=rejected,
            net_return=str(number(metrics['ending_equity_cny']) / number(initial_cash) - 1))
        results.append(metrics)
    return dict(experiment_version=EXPERIMENT_VERSION + '-shared-feedback-v1',
        rule_version=RULE_VERSION, symbols=symbols, folds=results, mode=mode,
        simultaneous_order_convention='TIMESTAMP_THEN_SYMBOL_ASCENDING_NOT_REAL_ORDER_PRIORITY',
        strict_pit_admitted=False, strict_oos_admitted=False, formal_eligibility=False,
        strategy_validation='NOT_PROVEN', action='no_order')
