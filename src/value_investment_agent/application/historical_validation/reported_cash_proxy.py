"""Join only matched period/scope/originals for a descriptive cash proxy."""
from decimal import Decimal
from ...domain.valuation.cash_capex_proxy import cash_capex_proxy


def reported_cash_proxies(review: dict) -> dict:
    if (review.get('schema_version') != 'disclosed-metric-review-v1' or review.get('action') != 'no_order'
            or review.get('financial_gate_admitted') is not False):
        raise ValueError('cash proxy requires non-admitted disclosed metrics')
    by_key = {}
    for fact in review['facts']:
        if fact['metric_name'] not in {'reported_operating_cash_flow', 'reported_cash_capex'}:
            continue
        if fact['unit'] != 'CNY' or fact.get('statement_scope') != 'CONSOLIDATED':
            raise ValueError('cash proxy requires consolidated CNY statement facts')
        key = (fact['metric_name'], fact['period'])
        if key in by_key:
            raise ValueError('duplicate cash proxy basis')
        by_key[key] = fact
    rows = []
    periods = sorted({period for _, period in by_key})
    for period in periods:
        cfo = by_key.get(('reported_operating_cash_flow', period))
        capex = by_key.get(('reported_cash_capex', period))
        if cfo is None or capex is None:
            rows.append(dict(period=period, status='NOT_ASSESSABLE', reason='Matched CFO/cash capex missing.'))
            continue
        if cfo['source_binding'] != capex['source_binding']:
            raise ValueError('cash proxy cannot combine different report originals')
        rows.append(dict(period=period, status='DESCRIPTIVE_PROXY_ONLY',
            cfo_cny=cfo['value'], cash_capex_cny=capex['value'],
            source_binding=cfo['source_binding'], physical_pages=[cfo['physical_page'], capex['physical_page']],
            **cash_capex_proxy(cfo=Decimal(cfo['value']), cash_capex=Decimal(capex['value']))))
    if not rows:
        raise ValueError('cash proxy requires explicit statement facts')
    return dict(schema_version='reported-cash-capex-proxy-v1', symbol=review['symbol'], rows=rows,
        financial_gate_admitted=False, dividend_sustainability_admitted=False,
        valuation_model_admitted=False, action='no_order')
