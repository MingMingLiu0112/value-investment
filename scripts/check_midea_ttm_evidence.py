"""Reconcile reviewed report cells; never approve a backtest or EPS value."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader
import pypdfium2 as pdfium


ROOT = Path(__file__).resolve().parents[1]
ANNUAL = 'runtime/historical-filing-index/20260908T041326996681Z/pdfs/000333-1222951181.pdf'
QUARTERS = 'runtime/historical-filing-index/20260908T124941550748Z/pdfs/'
REPURCHASES = 'runtime/historical-filing-index/20260908T153702487714Z/pdfs/'
CANCELLATION = 'runtime/historical-filing-index/20260908T154030826694Z/pdfs/'
REPORTS = [
    (ANNUAL, 'b17a9b9b84bca1d2a4e4a3cadc5dd5ba5c85e3f1fd2d758acd3315b5b040ecd9',
     {9: ['38,537,237'], 10: ['6,838,123', '38,538,987']}),
    (QUARTERS + '000333-1221570980.pdf',
     '684d66248c30b0d9f2ab1bdf3f85338ef48b6ede0b6ff0725b405ed82a32c51f',
     {9: ['31,699,114']}),
    (QUARTERS + '000333-1224767336.pdf',
     '9367216dcb6d6aaf15d3cfe5b7dc375b665eb3c8946d82d0725fefde48913a90',
     {5: ['97,345,744'], 8: ['37,883,383', '31,699,114']}),
    (REPURCHASES + '000333-1224706501.pdf',
     '9c17caab0fbbdc2d9f328d00704f4c3e4a5a56990da0e8e332f3226bfca08039',
     {1: ['20,564,598', '0.2679%'], 2: ['76,781,146', '0.9994%']}),
    (REPURCHASES + '000333-1224679428.pdf',
     '554724cfc92ee58257efc9cb595db5ff064d07642344f7cdd46dff21cf512713',
     {2: ['553,811', '注销完成后', '将及时披露回购注销完成']}),
    (CANCELLATION + '000333-1224890769.pdf',
     '8cb3d5bcfca9415e9e5ac940c925094f665bfc19b6dcf40f302d5688fcf625d2',
     {2: ['95,000,000', '2025年12月19日', '7,041,957,278', '6,946,957,278',
          '650,848,500', '7,692,805,778', '7,597,805,778']}),
]


def main():
    evidence = []
    for relative, expected, pages in REPORTS:
        path = ROOT / relative
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Original PDF hash mismatch: ' + relative)
        reader = PdfReader(path)
        with pdfium.PdfDocument(path) as document:
            for number, tokens in pages.items():
                text1 = reader.pages[number - 1].extract_text()
                page = document[number - 1]
                textpage = page.get_textpage()
                try:
                    text2 = textpage.get_text_range()
                finally:
                    textpage.close()
                    page.close()
                for token in tokens:
                    if token not in text1 or token not in text2:
                        raise ValueError(f'Reviewed cell absent: {relative} p{number}: {token}')
                evidence.append({'path': relative, 'sha256': expected,
                                 'pdf_page': number, 'reviewed_tokens': tokens})
    annual = Decimal('38537237')
    prior_ytd = Decimal('31699114')
    current_ytd = Decimal('37883383')
    fourth_quarter = annual - prior_ytd
    if fourth_quarter != Decimal('6838123'):
        raise ValueError('Annual fourth-quarter reconciliation failed')
    repurchase_a = 20564598
    repurchase_b = 76781146
    reported_account_shares = 97345744
    if repurchase_a + repurchase_b != reported_account_shares:
        raise ValueError('Repurchase plans do not reconcile to the reported account')
    before_a, after_a, h_shares = 7041957278, 6946957278, 650848500
    before_total, after_total, cancelled = 7692805778, 7597805778, 95000000
    if (before_a + h_shares != before_total or after_a + h_shares != after_total
            or before_a - after_a != cancelled or before_total - after_total != cancelled):
        raise ValueError('December cancellation share-class reconciliation failed')
    result = {
        'symbol': '000333', 'period_end': '2025-09-30',
        'accounting_basis': 'China enterprise accounting standards',
        'metric': 'parent_attributable_net_income', 'unit': 'CNY thousand',
        'annual_2024': str(annual), 'prior_2024_ytd': str(prior_ytd),
        'current_2025_ytd': str(current_ytd),
        'q4_2024_reconciled': str(fourth_quarter),
        'research_ttm_profit': str(annual + current_ytd - prior_ytd),
        'share_basis_research': {
            'as_of': '2025-09-30',
            'repurchase_plan_shares': [repurchase_a, repurchase_b],
            'reported_a_share_repurchase_account': reported_account_shares,
            'plan_sum_matches_quarterly_account': True,
            'planned_restricted_share_cancellation': 553811,
            'cancellation_completion_verified': False,
            'issued_ordinary_share_count': None,
            'outstanding_ordinary_share_count': None,
            'do_not_infer_total_shares_from_rounded_percentages': True,
            'independent_financial_source_verification': False,
        },
        'separate_december_cancellation': {
            'announcement_id': '1224890769',
            'effective_date_disclosed': '2025-12-19',
            'publication_date': '2025-12-23',
            'publication_intraday_verified': False,
            'cancelled_a_shares': cancelled,
            'issued_a_before': before_a, 'issued_a_after': after_a,
            'issued_h_before_and_after': h_shares,
            'issued_total_before': before_total, 'issued_total_after': after_total,
            'class_totals_and_cancellation_reconciled': True,
            'same_event_as_553811_restricted_share_proposal': False,
            'september_share_count_backfilled': False,
            'investor_position_reduction_applied': False,
            'financial_facts_verified': False,
        },
        'method': 'Reviewed cells with two-decoder token-presence checks and arithmetic reconciliation',
        'limitations': ['Token presence is not independent semantic extraction',
                       'Two decoders are not independent financial sources',
                       'Availability and ordinary-share scope not fully verified',
                       'Repurchase progress and quarterly filing are both issuer-origin evidence',
                       'Planned cancellation is not a completed share-count reduction',
                       'No EPS calculated; weighted share bases cannot be added'],
        'financial_facts_verified': False, 'backtest_ready': False,
        'evidence': evidence,
    }
    output = ROOT / 'runtime/midea-ttm-evidence-20260908.json'
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
