"""000568 H1-2026 case adapter; not a general issuer/period extractor."""
from value_investment_agent.infrastructure.filings.parent_funding_facts_v1 import (
    load_parent_facts, bind_original_page, bind_payment_arrangement,
)
from value_investment_agent.domain.research.parent_distribution_capacity_v1 import assess_capacity


def review_parent_funding(root, native_path, *, cutoff, period='2026-06-30'):
    packet = load_parent_facts(root, native_path, cutoff=cutoff)
    if period != '2026-06-30' or any(
            s.get('symbol') != '000568' for s in packet['sources'].values()):
        raise ValueError('unsupported issuer/period')
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
    h1 = packet['sources'][evidence[0]['source_id']]
    debt_evidence = [bind_original_page(root, h1, cutoff, page, amount)
                     for page, amount in [(40, '1,510,049,088.62'),
                                          (40, '1,220,000,000.00'),
                                          (40, '12,311,533,974.01'),
                                          (100, '1,508,700,000.00'),
                                          (100, '1,748,151.38'),
                                          (100, '7,689,071.11')]]
    capex = one('parent_capex')
    capex_evidence = bind_original_page(root, packet['sources'][capex['source_id']],
                                       cutoff, capex['physical_page'], '413,591,845.80')
    legal_evidence = bind_original_page(root, h1, cutoff, 40, '23,214,184,665.64')
    return dict(result=result, period=period, evidence=evidence,
                sources=packet['sources'], native_sha256=packet['native_sha256'],
                debt_evidence=debt_evidence, historical_capex=capex_evidence,
                future_necessary_investment='UNKNOWN',
                historical_cash_uses=dict(scope='parent', period='2026-H1', unit='CNY',
                    treatment='Already included in ending cash; no additional deduction.',
                    cash_statement_reconciliation='NOT_PERFORMED_OUT_OF_SCOPE'),
                retained_profit_evidence=legal_evidence, legal_adjustments='UNKNOWN',
                unknowns=['subsequent_parent_cash_bridge', 'principal_interest_maturity_split',
                          'operating_reserve', 'necessary_investment', 'legal_distribution_adjustments'],
                debt_review=dict(parent_current_noncurrent_liabilities='1510049088.62',
                    other_payables_including_dividend='12311533974.01',
                    other_payables_ex_dividend='5809966323.44',
                    other_payables_cash_timing='UNKNOWN',
                    parent_page=40, principal_interest_split=None,
                    parent_noncurrent_borrowing='1220000000.00',
                    consolidated_note_page=100,
                    consolidated_current_principal='1508700000.00',
                    consolidated_current_interest='1748151.38',
                    consolidated_current_lease='7689071.11',
                    warning='Consolidated components cannot be assigned to parent.'),
                interpretation='Historical static remainder is not current free cash; retained profit is not certified legal capacity.', action='no_order')


def review_post_h1(root, native_path, receipt_path, *, cutoff):
    review = review_parent_funding(root, native_path, cutoff=cutoff)
    review['post_h1_bridge'] = bind_payment_arrangement(root, receipt_path, cutoff)
    return review
