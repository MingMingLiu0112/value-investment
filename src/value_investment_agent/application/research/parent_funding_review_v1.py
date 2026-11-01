"""Historical parent funding review; future/current cash needs a separate bridge."""
from value_investment_agent.infrastructure.filings.parent_funding_facts_v1 import load_parent_facts
from value_investment_agent.domain.research.parent_distribution_capacity_v1 import assess_capacity


def review_parent_funding(root, native_path, *, cutoff, period='2026-06-30'):
    packet = load_parent_facts(root, native_path, cutoff=cutoff)
    def one(field):
        matches = [f for f in packet['facts'] if f['field'] == field and f['period_end'] == period]
        if len(matches) != 1:
            raise ValueError('missing/ambiguous parent fact: ' + field)
        return matches[0]
    evidence = [one(field) for field in (
        'parent_cash_equivalents', 'parent_dividend_payable', 'parent_retained_profit')]
    result = assess_capacity(opening_cash=evidence[0]['value'],
                             dividend_payable=evidence[1]['value'],
                             retained_profit=evidence[2]['value'], obligations=[])
    return dict(result=result, period=period, evidence=evidence,
                sources=packet['sources'], native_sha256=packet['native_sha256'],
                unknowns=['subsequent_parent_cash_bridge', 'principal_interest_maturity_split',
                          'operating_reserve', 'necessary_investment', 'legal_distribution_adjustments'],
                interpretation='Historical static remainder is not current free cash.', action='no_order')
