"""Build a matched-source cash statement change bridge from verified rows."""
from decimal import Decimal
from ...domain.valuation.operating_cash_bridge import operating_cash_change_bridge


def reported_cash_change(review: dict, *, current_period: str, prior_period: str) -> dict:
    if (review.get('schema_version') != 'disclosed-metric-review-v1'
            or review.get('action') != 'no_order' or review.get('financial_gate_admitted') is not False
            or current_period == prior_period):
        raise ValueError('cash bridge requires non-admitted distinct report periods')
    selected = [fact for fact in review['facts'] if fact['metric_name'].startswith('cash_bridge_')]
    by_period = {current_period: {}, prior_period: {}}
    bindings = []
    for fact in selected:
        if fact['period'] not in by_period:
            continue
        if (fact['unit'] != 'CNY' or fact.get('statement_scope') != 'CONSOLIDATED'
                or fact['verification_status'] != 'TRANSCRIBED_ROW_NUMERIC_MATCH_ONLY'):
            raise ValueError('cash bridge requires verified consolidated CNY rows')
        key = fact['metric_name'].removeprefix('cash_bridge_')
        if key in by_period[fact['period']]:
            raise ValueError('duplicate cash bridge component')
        by_period[fact['period']][key] = Decimal(fact['value'])
        bindings.append(fact['source_binding'])
    if not bindings or any(binding != bindings[0] for binding in bindings):
        raise ValueError('cash bridge must bind one report original')
    return dict(schema_version='reported-operating-cash-change-v1', symbol=review['symbol'],
        current_period=current_period, prior_period=prior_period, source_binding=bindings[0],
        **operating_cash_change_bridge(by_period[current_period], by_period[prior_period]))
