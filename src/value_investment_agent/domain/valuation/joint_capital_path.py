"""Conditional parent-equity capital ledger. No I/O, discounting or valuation."""
from decimal import Decimal, InvalidOperation, localcontext


HISTORICAL_FIELDS = frozenset({
    'revenue', 'cost', 'surcharges', 'selling', 'admin', 'research',
    'pre_tax_profit', 'tax', 'parent_profit', 'nonrecurring', 'da', 'cash',
})
DRIVER_FIELDS = frozenset({
    'years', 'retention', 'operating_allocation', 'new_operating_return',
    'new_liquidity_return', 'parent_cash_conversion', 'terminal_growth',
    'terminal_profit_scale',
})


def _number(value):
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int, Decimal)):
        raise ValueError('joint values require explicit decimal strings or Decimal')
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError('joint financial value is invalid') from None
    if not result.is_finite():
        raise ValueError('joint financial values must be finite')
    return result


def compile_joint_capital_path(*, start_book, profit_anchor, historical, drivers):
    """Derive five annual P/B/dividend/ROE rows from declared economic drivers.

Historical aggregates are not normalized forecasts. Future cash conversion and
maintenance=DA are explicit hypotheses, not certifications of upstream cash.
    """
    if set(historical) != HISTORICAL_FIELDS or set(drivers) != DRIVER_FIELDS:
        raise ValueError('joint path requires exact historical and driver fields')
    with localcontext() as ctx:
        ctx.prec = 48
        h = {key: _number(value) for key, value in historical.items()}
        d = {key: _number(value) for key, value in drivers.items() if key != 'years'}
        book, anchor = _number(start_book), _number(profit_anchor)
        if (book <= 0 or anchor <= 0 or h['revenue'] <= 0 or h['pre_tax_profit'] <= 0
                or not 0 <= h['tax'] < h['pre_tax_profit']
                or h['parent_profit'] <= 0 or h['da'] < 0
                or any(h[k] < 0 for k in ('cost', 'surcharges', 'selling', 'admin', 'research'))):
            raise ValueError('joint historical scope has unsupported financial signs')
        if abs(h['parent_profit'] - h['nonrecurring'] - anchor) > Decimal('.01'):
            raise ValueError('joint parent profit does not reconcile to the consumed anchor')
        tax_rate = h['tax'] / h['pre_tax_profit']
        parent_share = h['parent_profit'] / (h['pre_tax_profit'] - h['tax'])
        if not 0 < parent_share <= 1:
            raise ValueError('joint parent attribution must be within consolidated earnings')
        if (not 0 <= d['retention'] <= 1 or not 0 <= d['operating_allocation'] <= 1
                or not 0 <= d['new_operating_return'] <= 1
                or not 0 <= d['new_liquidity_return'] <= 1
                or not 0 <= d['parent_cash_conversion'] <= 1
                or not 0 <= d['terminal_growth'] <= Decimal('.10')
                or not 0 < d['terminal_profit_scale'] <= Decimal('2')):
            raise ValueError('joint research drivers exceed declared supported bounds')
        years = drivers['years']
        if (not isinstance(years, list) or len(years) != 5
                or any(not isinstance(row, dict) or set(row) != {'year', 'revenue_growth', 'cost_ratio'}
                       or type(row['year']) is not int or row['year'] != index
                       for index, row in enumerate(years, 1))):
            raise ValueError('joint path requires exactly five ordered explicit years')
        ratios = {key: h[key] / h['revenue'] for key in ('surcharges', 'selling', 'admin', 'research')}
        selected0 = h['revenue'] - h['cost'] - sum(h[k] for k in ratios)
        revenue, op_stock, liquid_stock, cash = h['revenue'], Decimal(0), Decimal(0), h['cash']
        rows = []
        for spec in years:
            growth, cost_ratio = _number(spec['revenue_growth']), _number(spec['cost_ratio'])
            if not Decimal('-.50') <= growth <= Decimal('.50') or not 0 <= cost_ratio <= 1:
                raise ValueError('joint annual growth/cost ratio outside supported bounds')
            revenue *= 1 + growth
            costs = revenue * cost_ratio
            expenses = sum(revenue * ratio for ratio in ratios.values())
            pbt = h['pre_tax_profit'] + revenue - costs - expenses - selected0
            legacy = pbt * (1 - tax_rate) * parent_share - h['nonrecurring']
            new_op = op_stock * d['new_operating_return']
            new_liquid = liquid_stock * d['new_liquidity_return']
            profit = legacy + new_op + new_liquid
            if profit < 0:
                raise ValueError('negative joint forecast profit is unsupported by the existing RI model')
            retained, dividend = profit * d['retention'], profit * (1 - d['retention'])
            op_add = retained * d['operating_allocation']
            liquid_add = retained - op_add
            closing = book + retained
            cash_close = cash + d['parent_cash_conversion'] * profit - op_add - dividend
            rows.append(dict(year=spec['year'], revenue=revenue, cost=costs,
                legacy_pre_tax_profit=pbt, legacy_parent_profit=legacy,
                new_operating_profit=new_op, new_liquidity_profit=new_liquid,
                profit=profit, opening_book=book, roe=profit / book, retained=retained,
                dividend=dividend, closing_book=closing, net_operating_addition=op_add,
                net_liquidity_addition=liquid_add, maintenance_capex_assumption=h['da'] * revenue / h['revenue'],
                cash_open=cash, cash_close=cash_close,
                cash_funding_status='PASS' if cash_close >= 0 else 'FAIL'))
            book, cash = closing, cash_close
            op_stock += op_add
            liquid_stock += liquid_add
        g = d['terminal_growth']
        p6 = rows[-1]['profit'] * (1 + g) * d['terminal_profit_scale']
        rho = p6 / book
        if rho <= 0 or g > rho:
            raise ValueError('joint terminal cannot self-fund the declared growth')
        return dict(forecast_roe=tuple(row['roe'] for row in rows), retention=d['retention'],
            terminal_roe=rho, terminal_growth=g, rows=rows, terminal_profit=p6,
            terminal_book=book, terminal_retention=g / rho,
            terminal_net_operating_investment=g * book, terminal_new_liquidity_investment=Decimal(0),
            terminal_dividend=p6 - g * book,
            cash_funding_status='PASS' if all(row['cash_close'] >= 0 for row in rows) else 'FAIL',
            scope='RESEARCH_ASSUMPTIONS_NOT_NORMALIZED_FACTS',
            limitations=('Maintenance equals scaled DA only by assumption.',
                        'Parent cash conversion and terminal marginal return remain unapproved.'))
