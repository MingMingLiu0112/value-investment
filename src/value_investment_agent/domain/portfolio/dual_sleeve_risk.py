"""Independent sleeve accounting and loss-budget review; never an order engine."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from ...portfolio_contracts import portfolio_input_bundle_from_payload
from ...portfolio_risk import build_portfolio_risk_assessment, security_risk_attributes_from_payload
from .sleeves import PortfolioSleeve, SharedSleeveBudget
from .security_attributes import SCHEMA as ATTRIBUTE_SCHEMA, parse_observed_attributes

CORE = 'CORE_VALUE'
HOTSPOT = 'HOTSPOT_SATELLITE'
SLEEVES = (CORE, HOTSPOT)
SCHEMA = 'dual-sleeve-risk-input-v1'
REPORT_SCHEMA = 'dual-sleeve-risk-review-v1'


def decimal(value, field, *, positive=False, fraction=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError(field + ' requires an explicit decimal')
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(field + ' requires a finite decimal') from error
    if not result.is_finite() or result < 0 or (positive and result <= 0):
        raise ValueError(field + ' out of range')
    if fraction and result > 1:
        raise ValueError(field + ' requires a fraction in [0,1]')
    return result


def timestamp(value, field):
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(field + ' requires a timezone timestamp') from error
    if result.utcoffset() is None:
        raise ValueError(field + ' requires a timezone timestamp')
    return result


def fields(payload, expected, label):
    if not isinstance(payload, dict) or set(payload) != set(expected):
        raise ValueError(label + ' fields missing or unknown')


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + ' requires nonempty text')
    return value


def digest(value, field):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError(field + ' requires exact SHA256')
    return value


def _blocked(namespace, blockers, generated_at):
    return dict(schema_version=REPORT_SCHEMA, action='no_order', status='BLOCKED_PRIVATE_INPUT',
        namespace=namespace, generated_at=generated_at.isoformat(), blockers=blockers,
        sleeves=None, aggregate=None, hotspot_quantity_review=None,
        position_guidance=None, expected_return=None, trade_eligible=False,
        acceptance_authority='NONE')


def review_dual_sleeve_risk(payload, *, generated_at, allow_synthetic=False, core_request=None):
    """Reuse one reconciled aggregate snapshot; allocate each share and cash once."""
    fields(payload, ('schema_version', 'action', 'namespace', 'portfolio', 'shared_budget',
        'sleeves', 'cash_reserve_cny', 'allocations', 'security_attributes', 'hotspot_request'), 'dual sleeve')
    if payload['schema_version'] != SCHEMA or payload['action'] != 'no_order':
        raise ValueError('unknown dual sleeve schema or action')
    namespace = payload['namespace']
    if namespace not in ('ACTUAL', 'SIMULATED') or (namespace == 'SIMULATED' and not allow_synthetic):
        raise ValueError('synthetic input requires explicit isolated permission')
    if not isinstance(generated_at, datetime) or generated_at.utcoffset() is None:
        raise ValueError('review requires timezone-aware generated_at')
    if payload['portfolio'] is None:
        result = _blocked(namespace, ['portfolio.private_input_missing'], generated_at)
        result['status'] = 'NOT_CONNECTED'
        return result
    bundle = portfolio_input_bundle_from_payload(payload['portfolio'])
    if bundle.snapshot.namespace != namespace:
        raise ValueError('portfolio and sleeve namespaces differ')
    missing = list(bundle.policy.missing_guidance_inputs())
    # SIMULATED is permitted only for explicitly isolated arithmetic tests.
    missing.extend(x for x in bundle.snapshot.missing_guidance_inputs() if x != 'actual_namespace')
    if missing:
        return _blocked(namespace, missing, generated_at)
    if any(payload[key] is None for key in ('shared_budget', 'sleeves', 'cash_reserve_cny', 'allocations')):
        return _blocked(namespace, ['sleeve_policy.private_input_missing'], generated_at)
    if generated_at < bundle.snapshot.available_at or (bundle.policy.confirmed_at
            and generated_at < bundle.policy.confirmed_at):
        raise ValueError('private inputs not available at review time')
    if bundle.snapshot.reconciled_at > generated_at:
        raise ValueError('reconciliation is in the future')
    if bundle.snapshot.as_of > generated_at.astimezone(ZoneInfo('Asia/Shanghai')).date():
        raise ValueError('snapshot date is in the future')
    attrs, attribute_gaps = {}, []
    if payload['security_attributes'] is None:
        return _blocked(namespace, ['security_attributes.missing'], generated_at)
    for item in payload['security_attributes']:
        if item.get('schema_version') == ATTRIBUTE_SCHEMA:
            attr = parse_observed_attributes(item, now=generated_at)
            attribute_gaps.extend('security_attributes.' + attr.symbol + '.' + gap + '.unknown' for gap in attr.gaps)
        else:
            attr = security_risk_attributes_from_payload(item)
        if attr.symbol in attrs:
            raise ValueError('duplicate security attributes')
        if not attr.evidence_refs:
            raise ValueError('risk attributes require evidence')
        attrs[attr.symbol] = attr
    needed = {h.symbol for h in bundle.snapshot.holdings}
    request = payload['hotspot_request']
    if request is not None:
        needed.add(request['symbol'])
    if core_request is not None:
        needed.add(core_request['symbol'])
    if needed - attrs.keys():
        return _blocked(namespace, ['security_attributes.missing',
            *['security_attributes.' + symbol + '.missing' for symbol in sorted(needed - attrs.keys())]], generated_at)
    for symbol in needed:
        item = next(row for row in payload['security_attributes'] if row['symbol'] == symbol)
        if item.get('schema_version') == ATTRIBUTE_SCHEMA:
            if timestamp(item['known_at'], 'attribute known_at').astimezone(ZoneInfo('Asia/Shanghai')).date() > bundle.snapshot.as_of:
                attribute_gaps.append('security_attributes.' + symbol + '.not_known_at_snapshot')
            holding = next((row for row in bundle.snapshot.holdings if row.symbol == symbol), None)
            if holding is not None and holding.exchange != item['exchange']:
                raise ValueError('Holding and official security exchange differ')
    shared = payload['shared_budget']
    fields(shared, ('core_value_budget', 'tactical_hotspot_budget', 'cash_floor',
        'cross_sleeve_single_stock_cap', 'cross_sleeve_sector_cap', 'policy_scope', 'action'), 'shared budget')
    budget = SharedSleeveBudget(**{key: decimal(value, key, fraction=True)
        if key not in ('policy_scope', 'action') else value for key, value in shared.items()})
    required_scope = 'SYNTHETIC_POLICY_ONLY' if namespace == 'SIMULATED' else 'USER_CONFIRMED'
    if budget.policy_scope != required_scope:
        raise ValueError('budget provenance and namespace differ')
    fields(payload['sleeves'], SLEEVES, 'sleeves')
    holdings = {h.symbol: h for h in bundle.snapshot.holdings}
    allocated = {symbol: Decimal(0) for symbol in holdings}
    rows = {sleeve: [] for sleeve in SLEEVES}
    seen = set()
    for allocation in payload['allocations']:
        fields({key: value for key, value in allocation.items() if key != 'cost_basis_cny'},
            ('sleeve', 'symbol', 'quantity', 'sellable_quantity',
             'committed_risk_cny', 'evidence_ref'), 'allocation')
        sleeve, symbol = allocation['sleeve'], allocation['symbol']
        if sleeve not in SLEEVES or symbol not in holdings or (sleeve, symbol) in seen:
            raise ValueError('unknown or duplicate sleeve allocation')
        seen.add((sleeve, symbol))
        text(allocation['evidence_ref'], 'allocation evidence')
        quantity = decimal(allocation['quantity'], 'allocation quantity', positive=True)
        sellable = decimal(allocation['sellable_quantity'], 'sellable quantity')
        if quantity != quantity.to_integral_value() or sellable != sellable.to_integral_value() or sellable > quantity:
            raise ValueError('share quantities must be integral; sellable cannot exceed holding')
        allocated[symbol] += quantity
        h = holdings[symbol]
        if h.cost_basis_cny is None:
            return _blocked(namespace, ['holding.cost_basis_missing'], generated_at)
        value = h.market_value_cny * quantity / h.quantity
        cost = (decimal(allocation['cost_basis_cny'], 'allocation cost')
                if 'cost_basis_cny' in allocation else h.cost_basis_cny * quantity / h.quantity)
        risk = (None if allocation['committed_risk_cny'] is None else
            decimal(allocation['committed_risk_cny'], 'committed risk'))
        rows[sleeve].append(dict(symbol=symbol, quantity=str(quantity), sellable_quantity=str(sellable),
            market_value_cny=str(value), cost_basis_cny=str(cost), unrealized_pnl_cny=str(value-cost),
            committed_risk_cny=None if risk is None else str(risk), industry=attrs[symbol].industry,
            common_factors='UNKNOWN' if getattr(attrs[symbol], 'gaps', ()) else list(attrs[symbol].common_factors)))
    if any(allocated[symbol] != h.quantity for symbol, h in holdings.items()):
        raise ValueError('sleeve quantities must exactly partition aggregate holdings')
    for symbol, holding in holdings.items():
        costs = sum((Decimal(row['cost_basis_cny']) for sleeve in SLEEVES
                     for row in rows[sleeve] if row['symbol'] == symbol), Decimal(0))
        if abs(costs - holding.cost_basis_cny) > Decimal('1E-20'):
            raise ValueError('sleeve costs must exactly partition aggregate cost')
    total = bundle.snapshot.cash_cny + sum((h.market_value_cny for h in holdings.values()), Decimal(0))
    if total <= 0:
        return _blocked(namespace, ['portfolio.nonpositive_equity'], generated_at)
    reserve = decimal(payload['cash_reserve_cny'], 'cash reserve')
    reviews, policies, alerts = {}, {}, list(attribute_gaps)
    fractions = {CORE: budget.core_value_budget, HOTSPOT: budget.tactical_hotspot_budget}
    for sleeve in SLEEVES:
        policy = payload['sleeves'][sleeve]
        fields({key: value for key, value in policy.items() if key != 'capital_budget_cny'},
            ('cash_cny', 'risk_budget_cny', 'max_single_security_fraction',
            'max_industry_fraction', 'max_factor_fraction', 'single_trade_risk_fraction',
            'single_security_risk_cny', 'realized_pnl_cny', 'financing_allowed',
            'risk_tools_allowed', 'confirmed_at', 'evidence_ref'), 'sleeve policy')
        required = ('cash_cny', 'risk_budget_cny', 'max_single_security_fraction',
            'max_industry_fraction', 'max_factor_fraction', 'financing_allowed', 'risk_tools_allowed',
            'confirmed_at', 'evidence_ref')
        if any(policy[key] is None for key in required):
            return _blocked(namespace, [sleeve + '.private_policy_incomplete'], generated_at)
        text(policy['evidence_ref'], 'sleeve policy evidence')
        if timestamp(policy['confirmed_at'], 'sleeve confirmed_at') > generated_at:
            raise ValueError('sleeve confirmation in future')
        if type(policy['financing_allowed']) is not bool or type(policy['risk_tools_allowed']) is not bool:
            raise ValueError('financing and risk tools require explicit user booleans')
        p = {key: decimal(policy[key], key, fraction=True) for key in
            ('max_single_security_fraction', 'max_industry_fraction', 'max_factor_fraction')}
        for key in ('cash_cny', 'risk_budget_cny'):
            p[key] = decimal(policy[key], key)
        for key in ('single_trade_risk_fraction', 'single_security_risk_cny'):
            p[key] = (None if policy[key] is None else decimal(policy[key], key,
                fraction=key.endswith('fraction')))
        if sleeve == HOTSPOT and any(p[key] is None for key in
                ('single_trade_risk_fraction', 'single_security_risk_cny')):
            return _blocked(namespace, ['hotspot.user_risk_policy_missing'], generated_at)
        pnl = policy['realized_pnl_cny']
        if pnl is not None:
            # Realized P&L can be negative; never infer it from a plan or cost basis.
            if isinstance(pnl, bool) or not isinstance(pnl, (str, int, Decimal)):
                raise ValueError('realized P&L requires explicit finite decimal')
            pnl = Decimal(pnl)
            if not pnl.is_finite():
                raise ValueError('realized P&L must be finite')
        used = sum((Decimal(r['market_value_cny']) for r in rows[sleeve]), Decimal(0))
        equity = used + p['cash_cny']
        limit = total * fractions[sleeve]
        if policy.get('capital_budget_cny') is not None:
            limit = min(limit, decimal(policy['capital_budget_cny'], 'capital budget'))
        known = all(r['committed_risk_cny'] is not None for r in rows[sleeve])
        committed = sum((Decimal(r['committed_risk_cny']) for r in rows[sleeve]), Decimal(0)) if known else None
        if equity > limit:
            alerts.append(sleeve + ':budget_exceeded')
        if committed is None:
            alerts.append(sleeve + ':risk_unknown')
        elif committed >= p['risk_budget_cny']:
            alerts.append(sleeve + ':risk_budget_exhausted')
        if policy['financing_allowed'] or policy['risk_tools_allowed']:
            alerts.append(sleeve + ':financing_or_risk_tools_not_supported')
        industry, factors = {}, {}
        for row in rows[sleeve]:
            value = Decimal(row['market_value_cny'])
            if value > equity * p['max_single_security_fraction']:
                alerts.append(sleeve + ':single_security_concentration:' + row['symbol'])
            industry[row['industry']] = industry.get(row['industry'], Decimal(0)) + value
            for factor in attrs[row['symbol']].common_factors:
                factors[factor] = factors.get(factor, Decimal(0)) + value
            if attrs[row['symbol']].liquidity_profile != 'LIQUID':
                alerts.append(sleeve + ':liquidity_review:' + row['symbol'])
        for label, values, cap in (('industry', industry, p['max_industry_fraction']),
                ('factor', factors, p['max_factor_fraction'])):
            alerts.extend(sleeve + ':' + label + '_concentration:' + key
                for key, value in values.items() if value > equity * cap)
        reviews[sleeve] = dict(contract_sleeve=(PortfolioSleeve.CORE_VALUE.value if sleeve == CORE
                else PortfolioSleeve.TACTICAL_HOTSPOT.value), budget_cny=str(limit),
            equity_cny=str(equity), used_funds_cny=str(used), cash_cny=str(p['cash_cny']),
            available_funds_cny=str(max(Decimal(0), min(p['cash_cny'], limit-used))),
            risk_budget_cny=str(p['risk_budget_cny']), committed_risk_cny=None if committed is None else str(committed),
            available_risk_cny=None if committed is None else str(max(Decimal(0), p['risk_budget_cny']-committed)),
            unrealized_pnl_cny=str(sum((Decimal(r['unrealized_pnl_cny']) for r in rows[sleeve]), Decimal(0))),
            realized_pnl_cny=None if pnl is None else str(pnl),
            full_capital_at_risk_cny=str(used), holdings=rows[sleeve],
            limits={key: str(p[key]) for key in ('max_single_security_fraction', 'max_industry_fraction', 'max_factor_fraction')},
            industry_exposure_cny={key: str(value) for key, value in industry.items()},
            factor_exposure_cny=(None if any('common_factors' in getattr(attrs[row['symbol']], 'gaps', ()) for row in rows[sleeve])
                else {key: str(value) for key, value in factors.items()}),
            exit_basis='FUNDAMENTAL_THESIS_AND_LIQUIDITY_REVIEW' if sleeve == CORE else 'PRICE_STRUCTURE_REVIEW',
            mechanical_stop_required=False if sleeve == CORE else None)
        policies[sleeve] = p
    if sum((policies[s]['cash_cny'] for s in SLEEVES), reserve) != bundle.snapshot.cash_cny:
        raise ValueError('cash must partition exactly; no borrowing or double reservation')
    if reserve < total * budget.cash_floor:
        alerts.append('shared:cash_floor_violation')
    assessment = (build_portfolio_risk_assessment(bundle=bundle, security_attributes=attrs,
        as_of=bundle.snapshot.as_of, generated_at=generated_at, assessment_id='dual-sleeve',
        assessment_namespace=namespace).as_policy() if attrs and not attribute_gaps else None)
    if assessment is not None:
        alerts.extend('aggregate:' + x for x in assessment['blockers'])
    elif bundle.snapshot.cash_cny < max(bundle.policy.minimum_cash_cny,
            (bundle.policy.emergency_cash_cny or Decimal(0))+(bundle.policy.liquidity_needs_cny or Decimal(0))):
        alerts.append('aggregate:reserved_cash')
    security_values = {symbol: h.market_value_cny for symbol, h in holdings.items()}
    industry_values = {}
    for symbol, value in security_values.items():
        key = attrs[symbol].industry
        industry_values[key] = industry_values.get(key, Decimal(0)) + value
    alerts.extend('shared:single_security_cap:' + symbol for symbol, value in security_values.items()
        if value > total * budget.cross_sleeve_single_stock_cap)
    alerts.extend('shared:industry_cap:' + key for key, value in industry_values.items()
        if value > total * budget.cross_sleeve_sector_cap)
    overlap = {symbol: [dict(sleeve=s, quantity=r['quantity'], market_value_cny=r['market_value_cny'])
        for s in SLEEVES for r in rows[s] if r['symbol'] == symbol] for symbol in holdings}
    overlap = {symbol: parts for symbol, parts in overlap.items() if len(parts) > 1}
    sizing = None
    if request is not None:
        sizing = _hotspot_review(request, bundle=bundle, total=total, budget=budget,
            reviews=reviews, policies=policies, attrs=attrs, security_values=security_values,
            industry_values=industry_values, generated_at=generated_at, alerts=alerts)
    if core_request is not None:
        core_sizing = _core_review(core_request, bundle=bundle, total=total, budget=budget,
            reviews=reviews, policies=policies, attrs=attrs, security_values=security_values,
            industry_values=industry_values, generated_at=generated_at, alerts=alerts)
    else:
        core_sizing = None
    return dict(schema_version=REPORT_SCHEMA, action='no_order', namespace=namespace,
        status='BLOCKED_PRIVATE_INPUT' if attribute_gaps else ('REVIEW_REQUIRED' if alerts else 'RISK_REVIEW_CALCULATED'), generated_at=generated_at.isoformat(),
        sensitivity='SIMULATED_DEMONSTRATION' if namespace == 'SIMULATED' else 'PRIVATE_USER_CONFIRMED',
        blockers=list(dict.fromkeys(alerts)), sleeves=reviews,
        aggregate=dict(total_assets_cny=str(total), cash_cny=str(bundle.snapshot.cash_cny),
            reserve_cny=str(reserve), duplicated_security_exposure=overlap, existing_risk_assessment=assessment,
            security_attribute_gaps=attribute_gaps,
            committed_risk_total_cny=(str(sum((Decimal(r['committed_risk_cny']) for s in SLEEVES for r in rows[s]), Decimal(0)))
                if all(r['committed_risk_cny'] is not None for s in SLEEVES for r in rows[s]) else None)),
        hotspot_quantity_review=sizing, **({'core_quantity_review': core_sizing} if core_request is not None else {}),
        position_guidance=None, expected_return=None,
        trade_eligible=False, acceptance_authority='NONE')


def _hotspot_review(request, *, bundle, total, budget, reviews, policies, attrs,
        security_values, industry_values, generated_at, alerts):
    fields(request, ('sleeve', 'symbol', 'entry_price_cny', 'stop_price_cny', 'gap_stress_cny',
        'entry_slippage_cny', 'exit_slippage_cny', 'buy_fee_fraction', 'sell_fee_fraction',
        'minimum_buy_fee_cny', 'minimum_sell_fee_cny', 'lot_size', 'max_trade_notional_cny',
        'quote_as_of', 'available_at', 'valid_until', 'liquidity_verified', 'limit_up',
        'limit_down', 'research_version_sha256', 'evidence_ref'), 'hotspot request')
    if request['sleeve'] != HOTSPOT:
        raise ValueError('loss-based sizing is only for HOTSPOT_SATELLITE; core has no mechanical stop')
    symbol = request['symbol']
    digest(request['research_version_sha256'], 'research version')
    text(request['evidence_ref'], 'hotspot input evidence')
    for key in ('liquidity_verified', 'limit_up', 'limit_down'):
        if type(request[key]) is not bool:
            raise ValueError(key + ' requires a boolean')
    lot = request['lot_size']
    if type(lot) is not int or lot <= 0:
        raise ValueError('lot_size requires explicit positive integer trading unit')
    values = {key: decimal(request[key], key, fraction=key.endswith('fraction')) for key in
        ('entry_price_cny', 'stop_price_cny', 'gap_stress_cny', 'entry_slippage_cny',
        'exit_slippage_cny', 'buy_fee_fraction', 'sell_fee_fraction',
        'minimum_buy_fee_cny', 'minimum_sell_fee_cny', 'max_trade_notional_cny')}
    entry, stop = values['entry_price_cny'], values['stop_price_cny']
    if not 0 < stop < entry:
        raise ValueError('hotspot stop must be positive and below entry')
    available = timestamp(request['available_at'], 'quote available_at')
    expiry = timestamp(request['valid_until'], 'quote valid_until')
    reasons = list(alerts)
    if (request['quote_as_of'] != bundle.snapshot.as_of.isoformat()
            or available > generated_at or expiry < generated_at or expiry < available):
        reasons.append('hotspot:stale_or_future_input')
    if not request['liquidity_verified'] or attrs[symbol].liquidity_profile != 'LIQUID':
        reasons.append('hotspot:liquidity_unknown_or_restricted')
    if request['limit_up'] or request['limit_down']:
        reasons.append('hotspot:price_limit_execution_risk')
    review, policy = reviews[HOTSPOT], policies[HOTSPOT]
    same_risk = [r['committed_risk_cny'] for sleeve in SLEEVES for r in reviews[sleeve]['holdings'] if r['symbol'] == symbol]
    if review['available_risk_cny'] is None or any(r is None for r in same_risk):
        reasons.append('hotspot:committed_risk_unknown')
    # Conservative vetoes are explicit; core cash/risk never funds this calculation.
    if reasons:
        return dict(status='BLOCKED', blockers=list(dict.fromkeys(reasons)), review_quantity=None,
            stop_execution_guaranteed=False, t_plus_one=True, trade_eligible=False)
    equity = Decimal(review['equity_cny'])
    risk_limit = min(equity * policy['single_trade_risk_fraction'], Decimal(review['available_risk_cny']),
        max(Decimal(0), policy['single_security_risk_cny']-sum((Decimal(x) for x in same_risk), Decimal(0))))
    buy_price = entry + values['entry_slippage_cny']
    stress_exit = max(Decimal(0), stop-values['gap_stress_cny']-values['exit_slippage_cny'])
    capital_limit = _capital_limit(symbol, HOTSPOT, values['max_trade_notional_cny'],
        bundle=bundle, total=total, budget=budget, reviews=reviews, policies=policies,
        attrs=attrs, security_values=security_values, industry_values=industry_values)
    def amounts(quantity):
        buy = buy_price * quantity
        sell = stress_exit * quantity
        buy_fee = max(values['minimum_buy_fee_cny'], buy*values['buy_fee_fraction']) if quantity else Decimal(0)
        sell_fee = max(values['minimum_sell_fee_cny'], sell*values['sell_fee_fraction']) if quantity else Decimal(0)
        return buy+buy_fee, (buy-sell)+buy_fee+sell_fee
    low, high = 0, int(capital_limit/buy_price/lot)
    while low < high:
        middle = (low+high+1)//2
        cost, risk = amounts(middle*lot)
        if cost <= capital_limit and risk <= risk_limit:
            low = middle
        else:
            high = middle-1
    quantity = low*lot
    cost, risk = amounts(quantity)
    blockers = [] if quantity else ['hotspot:budget_below_one_lot']
    if not quantity and amounts(lot)[0] > Decimal(review['available_funds_cny']):
        blockers.append(HOTSPOT + ':sleeve_cash_budget_insufficient')
    return dict(status='QUANTITY_REVIEW_ONLY' if quantity else 'BLOCKED_BELOW_ONE_LOT',
        blockers=blockers, review_quantity=quantity,
        symbol=symbol, sleeve=HOTSPOT, planned_risk_limit_cny=str(risk_limit),
        same_security_existing_risk_cny=str(sum((Decimal(x) for x in same_risk), Decimal(0))),
        stressed_loss_cny=str(risk), cash_required_cny=str(cost), stressed_exit_price_cny=str(stress_exit),
        full_capital_at_risk_cny=str(cost), stop_execution_guaranteed=False, t_plus_one=True,
        same_day_exit_available=False, trade_eligible=False,
        formula='q*(entry+entry_slippage-max(0,stop-gap-exit_slippage))+buy_fee+sell_fee',
        limitations=['T+1 prevents guaranteed same-day exit', 'Gaps and price limits can exceed stress assumptions',
            'Stop price is not a guaranteed execution price', 'Manual research and entry gates remain required'])


def _capital_limit(symbol, sleeve, tranche, *, bundle, total, budget, reviews,
        policies, attrs, security_values, industry_values):
    review, policy = reviews[sleeve], policies[sleeve]
    equity = Decimal(review['equity_cny'])
    same_value = sum((Decimal(r['market_value_cny']) for r in review['holdings'] if r['symbol'] == symbol), Decimal(0))
    industry = attrs[symbol].industry
    sleeve_industry = Decimal(review['industry_exposure_cny'].get(industry, '0'))
    capital_limit = min(Decimal(review['available_funds_cny']), tranche,
        max(Decimal(0), bundle.snapshot.cash_cny-max(bundle.policy.minimum_cash_cny,
            (bundle.policy.emergency_cash_cny or Decimal(0))+(bundle.policy.liquidity_needs_cny or Decimal(0)))),
        max(Decimal(0), equity*policy['max_single_security_fraction']-same_value),
        max(Decimal(0), equity*policy['max_industry_fraction']-sleeve_industry),
        max(Decimal(0), total*budget.cross_sleeve_single_stock_cap-security_values.get(symbol, Decimal(0))),
        max(Decimal(0), total*budget.cross_sleeve_sector_cap-industry_values.get(industry, Decimal(0))),
        max(Decimal(0), total*bundle.policy.max_single_security_pct/100-security_values.get(symbol, Decimal(0))),
        max(Decimal(0), total*bundle.policy.max_single_industry_pct/100-industry_values.get(industry, Decimal(0))))
    if attrs[symbol].cyclical and bundle.policy.max_cyclical_exposure_pct is not None:
        existing_cyclical = sum((value for held_symbol, value in security_values.items()
            if attrs[held_symbol].cyclical), Decimal(0))
        capital_limit = min(capital_limit, max(Decimal(0),
            total*bundle.policy.max_cyclical_exposure_pct/100-existing_cyclical))
    for factor in attrs[symbol].common_factors:
        capital_limit = min(capital_limit, max(Decimal(0), equity*policy['max_factor_fraction']
            -Decimal(review['factor_exposure_cny'].get(factor, '0'))),
            max(Decimal(0), total*min(policies[s]['max_factor_fraction'] for s in SLEEVES)
                -sum((Decimal(reviews[s]['factor_exposure_cny'].get(factor, '0')) for s in SLEEVES), Decimal(0))))
    return capital_limit


def _core_review(request, *, bundle, total, budget, reviews, policies, attrs,
        security_values, industry_values, generated_at, alerts):
    fields(request, ('symbol', 'entry_price_cny', 'entry_slippage_cny', 'buy_fee_fraction',
        'minimum_buy_fee_cny', 'lot_size', 'max_trade_notional_cny', 'available_at',
        'valid_until', 'quote_as_of', 'liquidity_verified', 'limit_up', 'limit_down'), 'core request')
    symbol = request['symbol']
    values = {key: decimal(request[key], key, fraction=key.endswith('fraction')) for key in
        ('entry_price_cny', 'entry_slippage_cny', 'buy_fee_fraction', 'minimum_buy_fee_cny', 'max_trade_notional_cny')}
    price = decimal(request['entry_price_cny'], 'entry price', positive=True) + values['entry_slippage_cny']
    lot = request['lot_size']
    if type(lot) is not int or lot <= 0:
        raise ValueError('CORE requires an explicit positive integer trading unit')
    if any(type(request[key]) is not bool for key in ('liquidity_verified', 'limit_up', 'limit_down')):
        raise ValueError('CORE execution choices require booleans')
    reasons = list(alerts)
    available, expiry = timestamp(request['available_at'], 'available_at'), timestamp(request['valid_until'], 'valid_until')
    if (available > generated_at or expiry < generated_at or expiry < available
            or request['quote_as_of'] != bundle.snapshot.as_of.isoformat()):
        reasons.append('core:stale_or_future_input')
    if not request['liquidity_verified'] or attrs[symbol].liquidity_profile != 'LIQUID':
        reasons.append('core:liquidity_unknown_or_restricted')
    if request['limit_up'] or request['limit_down']:
        reasons.append('core:price_limit_execution_risk')
    if reasons:
        return dict(status='BLOCKED', blockers=list(dict.fromkeys(reasons)), review_quantity=None, trade_eligible=False)
    capital_limit = _capital_limit(symbol, CORE, values['max_trade_notional_cny'],
        bundle=bundle, total=total, budget=budget, reviews=reviews, policies=policies,
        attrs=attrs, security_values=security_values, industry_values=industry_values)
    def cost(quantity):
        gross = quantity * price
        return gross + max(values['minimum_buy_fee_cny'], gross * values['buy_fee_fraction']) if quantity else Decimal(0)
    low, high = 0, int(capital_limit/price/lot)
    while low < high:
        middle = (low+high+1)//2
        if cost(middle*lot) <= capital_limit:
            low = middle
        else:
            high = middle-1
    quantity = low*lot
    blockers = [] if quantity else ['core:budget_below_one_lot']
    if not quantity and cost(lot) > Decimal(reviews[CORE]['available_funds_cny']):
        blockers.append(CORE + ':sleeve_cash_budget_insufficient')
    return dict(status='QUANTITY_REVIEW_ONLY' if quantity else 'BLOCKED_BELOW_ONE_LOT',
        blockers=blockers, review_quantity=quantity,
        symbol=symbol, sleeve=CORE, cash_required_cny=str(cost(quantity)), capital_limit_cny=str(capital_limit),
        tranche_budget_cny=str(values['max_trade_notional_cny']), mechanical_stop_required=False,
        exit_basis='FUNDAMENTAL_THESIS_AND_LIQUIDITY_REVIEW', trade_eligible=False)
