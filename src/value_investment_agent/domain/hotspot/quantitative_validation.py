"""Deterministic execution of frozen orders; no signal fitting or admission."""
from collections import Counter
from datetime import datetime, time as clock_time
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from ..execution.exchange_calendar import is_exchange_session, next_exchange_session

CHINA = ZoneInfo("Asia/Shanghai")


def evaluate_economic_validation_draft(protocol, blocks, *, window_uncertainty=None):
    """Arithmetic/coverage review only; a draft never grants strategy admission."""
    if (protocol.get('schema_version') != 'hotspot-economic-validation-draft-v1'
            or protocol.get('status') != 'DRAFT' or protocol.get('action') != 'no_order'
            or type(protocol.get('block_sessions')) is not int or protocol.get('block_sessions') != 42
            or type(protocol.get('block_count')) is not int or protocol.get('block_count') != 3
            or protocol.get('block_acceptance') != 'ALL_THREE_BLOCKS_MUST_MEET_EXPLICIT_POLICY'
            or protocol.get('benchmarks') != ['CASH', 'SAME_POOL_EQUAL_WEIGHT']
            or protocol.get('cost_multipliers') != ['0', '1', '2']):
        raise ValueError('Unsupported economic draft contract')
    policy = protocol['economic_policy']
    full_window_uncertainty = policy.get('uncertainty_application') == 'FULL_126_SESSION_WINDOW'
    checks = []

    def check(name, status, reason):
        checks.append(dict(check=name, status=status, reason=reason))

    missing = [key for key in ('minimum_excess_cash', 'minimum_excess_pool',
        'maximum_drawdown', 'minimum_trades', 'uncertainty_method', 'uncertainty_parameters',
        'minimum_excess_lower_bound', 'cost_evaluation')
        if policy.get(key) is None]
    check('ECONOMIC_POLICY_COMPLETE', 'INSUFFICIENT_DATA' if missing else 'PASS',
          'Missing: ' + ', '.join(missing) if missing else 'Explicit caller-supplied draft policy')
    if missing:
        policy_usable = False
    else:
        policy_usable = True
        maximum = number(policy['maximum_drawdown'])
        if (not 0 < maximum <= 1 or type(policy['minimum_trades']) is not int
                or policy['minimum_trades'] < 1 or not isinstance(policy['uncertainty_method'], str)
                or not policy['uncertainty_method'].strip()
                or not isinstance(policy['uncertainty_parameters'], dict)
                or policy['cost_evaluation'] not in {'BASE_NET_WITH_0X_2X_DISCLOSURE', 'BASE_NET_WITH_2X_CASH_FLOOR'}):
            raise ValueError('Invalid explicit economic risk/sample policy')
        for key in ('minimum_excess_cash', 'minimum_excess_pool', 'minimum_excess_lower_bound'):
            number(policy[key])
    if not isinstance(blocks, list) or len(blocks) > 3:
        raise ValueError('Bounded three-block results required')
    complete = len(blocks) == 3
    check('THREE_BLOCK_COVERAGE', 'PASS' if complete else 'INSUFFICIENT_DATA',
          'Require three non-overlapping complete 42-session blocks')
    previous = None
    for index, block in enumerate(blocks):
        sessions = block['sessions']
        if (not isinstance(sessions, list) or len(sessions) != 42
                or sessions != sorted(set(sessions))):
            raise ValueError('Exactly 42 distinct ordered sessions per block required')
        days = [datetime.fromisoformat(day).date() for day in sessions]
        if (any(day.isoformat() != text or not is_exchange_session('SSE', day)
                for day, text in zip(days, sessions)) or (previous and days[0] <= previous)):
            raise ValueError('Disjoint covered exchange session dates required')
        if previous and days[0] != next_exchange_session('SSE', previous):
            raise ValueError('Omitted exchange session between blocks')
        # Prevent dropped losing days from masquerading as a complete block.
        from datetime import timedelta
        day, expected = days[0], []
        while day <= days[-1]:
            if is_exchange_session('SSE', day):
                expected.append(day.isoformat())
            day += timedelta(days=1)
        if expected != sessions:
            raise ValueError('Omitted exchange session inside block')
        previous = days[-1]
        if block.get('scope') != 'PAIRED_SAME_POOL_PORTFOLIO_NET_OF_COST':
            check(f'BLOCK_{index + 1}_COMPARABILITY', 'INSUFFICIENT_DATA',
                  'Isolated security returns or gross benchmarks are not paired portfolio returns')
            continue
        sensitivity = block.get('cost_returns')
        if not isinstance(sensitivity, dict) or set(sensitivity) != {'0', '1', '2'}:
            check(f'BLOCK_{index + 1}_COST_SENSITIVITY', 'INSUFFICIENT_DATA',
                  'Net 0x/1x/2x cost results required')
            continue
        for value in sensitivity.values():
            if type(value) is bool or not Decimal(str(value)).is_finite() or Decimal(str(value)) < -1:
                raise ValueError('Invalid cost sensitivity return')
        metrics = {}
        keys = ('strategy_net_return', 'cash_net_return', 'pool_net_return')
        if not full_window_uncertainty:
            keys += ('excess_lower_bound',)
        for key in keys:
            if type(block[key]) is bool:
                raise ValueError('Boolean is not an economic metric')
            value = Decimal(str(block[key]))
            if not value.is_finite() or (key != 'excess_lower_bound' and value < -1):
                raise ValueError('Finite fractional economic returns required')
            metrics[key] = value
        if Decimal(str(sensitivity['1'])) != metrics['strategy_net_return']:
            raise ValueError('Base cost result differs from strategy net return')
        drawdown = number(block['maximum_drawdown'])
        if drawdown > 1 or type(block['trade_count']) is not int or block['trade_count'] < 0:
            raise ValueError('Invalid drawdown or trade count')
        if drawdown < max(Decimal(0), -metrics['strategy_net_return']):
            raise ValueError('Drawdown contradicts loss from initial equity')
        if not policy_usable:
            continue
        if (block['uncertainty_method'] != policy['uncertainty_method']
                or block.get('uncertainty_parameters') != policy['uncertainty_parameters']
                or block['trade_count'] < policy['minimum_trades']):
            check(f'BLOCK_{index + 1}_SAMPLE', 'INSUFFICIENT_DATA',
                  'Predeclared uncertainty method and sample requirement not met')
            continue
        passed = (metrics['strategy_net_return'] - metrics['cash_net_return'] > number(policy['minimum_excess_cash'])
            and metrics['strategy_net_return'] - metrics['pool_net_return'] > number(policy['minimum_excess_pool'])
            and drawdown <= number(policy['maximum_drawdown'])
            and (full_window_uncertainty or
                 metrics['excess_lower_bound'] > number(policy['minimum_excess_lower_bound'])))
        if policy['cost_evaluation'] == 'BASE_NET_WITH_2X_CASH_FLOOR':
            passed = passed and Decimal(str(sensitivity['2'])) >= metrics['cash_net_return']
        check(f'BLOCK_{index + 1}_ECONOMIC_COMPARISON', 'PASS' if passed else 'FAIL',
              'Net benchmark excess, risk cap and supplied uncertainty bound; not authenticity verification')
    if full_window_uncertainty:
        if window_uncertainty is None:
            check('FULL_WINDOW_UNCERTAINTY', 'INSUFFICIENT_DATA',
                  '126-day continuous paired series required; do not splice reset fold accounts')
        else:
            if (window_uncertainty['method'] != policy['uncertainty_method']
                    or window_uncertainty['parameters'] != policy['uncertainty_parameters']
                    or type(window_uncertainty['observed_days']) is not int
                    or window_uncertainty['observed_days'] != 126):
                raise ValueError('Full-window uncertainty contract mismatch')
            enough = 126 >= policy['uncertainty_parameters']['block_length'] * policy['uncertainty_parameters']['minimum_effective_blocks']
            bounds = [Decimal(str(window_uncertainty[key])) for key in
                      ('cash_excess_lower_bound', 'pool_excess_lower_bound')]
            if not all(value.is_finite() for value in bounds):
                raise ValueError('Finite full-window bounds required')
            check('FULL_WINDOW_UNCERTAINTY', 'INSUFFICIENT_DATA' if not enough else
                  'PASS' if all(value > number(policy['minimum_excess_lower_bound']) for value in bounds) else 'FAIL',
                  'Declared full-window paired bounds; no independent coverage or OOS attestation')
    verdict = ('FAIL' if any(c['status'] == 'FAIL' for c in checks) else
               'INSUFFICIENT_DATA' if any(c['status'] == 'INSUFFICIENT_DATA' for c in checks) else 'PASS')
    return dict(checks=checks, economic_evaluation=verdict, status='NOT_ADMITTED',
        evaluation_scope='DRAFT_ARITHMETIC_NOT_VERIFIED_STRATEGY_OOS',
        actual_sample_accepted=False, strict_oos_admitted=False, strict_pit_admitted=False,
        strategy_validation='NOT_PROVEN', formal_eligibility=False, action='no_order')


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


def compare_frozen_portfolio_accounts(protocol, strategy_inputs_by_cost, benchmark_orders_by_cost, fold,
                                      *, benchmark_preflight_by_cost=None):
    """One shared cash account per lane; frozen intents are not adaptive signals."""
    initial = number(protocol['initial_cash_cny'])
    results = []
    for multiplier in (Decimal(0), Decimal(1), Decimal(2)):
        strategy_inputs = strategy_inputs_by_cost[str(multiplier)]
        benchmark_orders = benchmark_orders_by_cost[str(multiplier)]
        strategy = simulate_fold(protocol, strategy_inputs, fold, cost_multiplier=multiplier)
        benchmark = simulate_fold(protocol, dict(bars=strategy_inputs['bars'], orders=benchmark_orders),
                                  fold, cost_multiplier=multiplier)
        for lane, preflight, count in (
            (strategy, strategy_inputs.get('preflight_rejected', []),
             strategy_inputs.get('frozen_intention_count', len(strategy_inputs['orders']))),
            (benchmark, (benchmark_preflight_by_cost or {}).get(str(multiplier), []), None),
        ):
            rejected = [*lane['rejected_orders'], *preflight]
            identities = [row['order_id'] for row in rejected] + [row['order_id'] for row in lane['fills']]
            if len(identities) != len(set(identities)) or (count is not None and count != len(identities)):
                raise ValueError('Frozen intent outcomes must reconcile without duplicate or lost rejects')
            lane.update(rejected_orders=rejected, rejection_counts=dict(Counter(row['reason'] for row in rejected)),
                frozen_intention_count=len(identities), unfilled_count=len(rejected),
                unfilled_rate=str(Decimal(len(rejected)) / len(identities)) if identities else None)
        strategy_return = number(strategy['ending_equity_cny']) / initial - 1
        benchmark_return = number(benchmark['ending_equity_cny']) / initial - 1
        last_marks = {}
        for bar in sorted(strategy_inputs['bars'], key=lambda row: stamp(row['time'])):
            last_marks[bar['symbol']] = number(bar['close'])
        for lane in (strategy, benchmark):
            inventory = {}
            for fill in lane['fills']:
                inventory[fill['symbol']] = inventory.get(fill['symbol'], 0) + (
                    fill['quantity'] if fill['side'] == 'BUY' else -fill['quantity'])
            nav = number(lane['ending_equity_cny'])
            lane['ending_weights'] = {symbol: str(quantity * last_marks[symbol] / nav)
                for symbol, quantity in inventory.items() if quantity and nav}
            lane['ending_cash_weight'] = str(number(lane['ending_cash_cny']) / nav) if nav else None
        curves = []
        for lane in (strategy, benchmark):
            daily = {}
            for point in lane['equity_curve']:
                local = stamp(point['time']).astimezone(CHINA)
                if local.time() == clock_time(15):
                    daily[local.date().isoformat()] = number(point['equity_cny'])
            curves.append(daily)
        if set(curves[0]) != set(curves[1]):
            raise ValueError('Paired portfolio mark dates differ')
        paired, previous_strategy, previous_benchmark = [], initial, initial
        for day in sorted(curves[0]):
            current_strategy, current_benchmark = curves[0][day], curves[1][day]
            if previous_strategy <= 0 or previous_benchmark <= 0:
                raise ValueError('Positive prior NAV required for paired returns')
            strategy_daily = current_strategy / previous_strategy - 1
            benchmark_daily = current_benchmark / previous_benchmark - 1
            excess = strategy_daily - benchmark_daily
            paired.append(dict(date=day, daily_excess_return=str(excess),
                strategy_daily_return=str(strategy_daily), benchmark_daily_return=str(benchmark_daily),
                daily_excess_cash=str(strategy_daily), daily_excess_pool=str(excess)))
            previous_strategy, previous_benchmark = current_strategy, current_benchmark
        values = [Decimal(row['daily_excess_return']) for row in paired]
        loo = [(sum(values) - value) / (len(values) - 1) for value in values] if len(values) > 1 else []
        results.append(dict(cost_multiplier=str(multiplier), strategy=strategy, benchmark=benchmark,
            initial_cash_cny=str(initial), strategy_net_return=str(strategy_return),
            benchmark_net_return=str(benchmark_return), cash_net_return='0',
            cash_assumption='ZERO_INTEREST_ZERO_FEES_CNY_CASH_NOT_ACCOUNT_YIELD',
            excess_to_cash=str(strategy_return), excess_to_pool=str(strategy_return - benchmark_return),
            paired_daily_excess=paired, uncertainty=dict(
                method='LEAVE_ONE_DAY_OUT_MEAN_PAIRED_EXCESS_SENSITIVITY_NOT_CONFIDENCE_INTERVAL',
                lower=str(min(loo)) if loo else None, upper=str(max(loo)) if loo else None,
                units='DAILY_RETURN_FRACTION', statistical_coverage_claim=False)))
    return dict(fold=fold, scenarios=results,
        simultaneous_order_convention='TIMESTAMP_THEN_SYMBOL_ASCENDING_NOT_REAL_ORDER_PRIORITY',
        scope='SHARED_CASH_FROZEN_INTENT_DIAGNOSTIC_NOT_ADAPTIVE_STRATEGY_VALIDATION',
        assumptions=['RETROSPECTIVE_COHORT', 'ASSUMED_TRADABILITY_AND_COSTS',
            'NO_FEEDBACK_REGENERATION_AFTER_SHARED_ACCOUNT_REJECTION',
            'EX_POST_BAR_TURNOVER_LIQUIDITY_NOT_KNOWN_AT_ORDER',
            'NO_FORCED_TERMINAL_LIQUIDATION_UNREALIZED_MARKS_RETAINED',
            'NO_CORPORATE_ACTION_RECONCILIATION'],
        strategy_validation='NOT_PROVEN', strict_pit_admitted=False, strict_oos_admitted=False,
        formal_eligibility=False, performance_claim_allowed=False, action='no_order')
