"""Real 2025 cash distribution, hypothetical settlements; not strategy returns."""
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re

from pypdf import PdfReader
import pypdfium2 as pdfium

from value_investment_agent.dividend_tax_lots import ACCOUNT, DividendTaxLots, TaxDistribution


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / 'runtime/historical-filing-index/20260908T062537893160Z/pdfs/600519-1223934491.pdf'
PDF_HASH = '8ff3e6e370c75cece700e5474337c8ecf1adb87b01a1a696bae02fd25982af3b'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (date, Decimal)):
        return str(value)
    raise TypeError(type(value).__name__)


def main():
    if digest(PDF) != PDF_HASH:
        raise ValueError('Original announcement changed')
    reader = PdfReader(PDF)
    checks = {0: ['600519', '27.673', '2025/6/25', '2025/6/26'],
              2: ['仅进行现金红利分配，不送股和转增股本'],
              3: ['公司暂不扣缴个人所得税', '实际税负为20%', '实际税负为10%']}
    verified = []
    with pdfium.PdfDocument(PDF) as document:
        for index, fragments in checks.items():
            page = document[index]
            textpage = page.get_textpage()
            texts = [reader.pages[index].extract_text(), textpage.get_text_range()]
            textpage.close()
            page.close()
            for fragment in fragments:
                if any(fragment not in re.sub(r'\s+', '', text) for text in texts):
                    raise ValueError(f'Original text check failed: page {index+1}: {fragment}')
            verified.append({'physical_page': index + 1, 'fragments': fragments})

    book = DividendTaxLots(account_id='hypothetical-cash-tax-validation',
                           symbol='600519', account_type=ACCOUNT)
    inputs = [('2024-06-14', 100, 0), ('2025-06-16', 100, 0),
              ('2025-06-25', 0, 0), ('2025-06-27', 0, 150), ('2025-07-17', 0, 50)]
    results = []
    event = TaxDistribution('cninfo:1223934491', date(2025, 6, 25),
                            Decimal('27.673'), PDF_HASH)
    for text, bought, sold in inputs:
        current = date.fromisoformat(text)
        results.append(book.close(current, bought=bought, sold=sold,
                                   distributions=(event,) if current == event.record_date else ()))
    # Independent rational arithmetic uses the declared dates and notice rates,
    # not the tax function, its anniversary helper or batch allocations.
    first_expected = Fraction(27673, 1000) * 50 / 5
    second_expected = Fraction(27673, 1000) * 50 / 10
    actual = []
    for result in results[-2:]:
        actual.append(sum((item['calculation'].additional_tax
                           for lot in result['disposals'] for item in lot['taxes']), Decimal(0)))
    if list(map(Fraction, actual)) != [first_expected, second_expected]:
        raise ValueError('Independent tax reconciliation failed')
    if results[-1]['closing_shares'] != 0:
        raise ValueError('Closing tax shares mismatch')
    if sum(x['taxable_income'] for x in results[2]['entitlements']) != Decimal('5534.600'):
        raise ValueError('Actual cash per share confused with ex reference')
    out = ROOT / 'runtime/strategy-validation' / ('moutai-cash-tax-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    payload = {'scope': 'real cash notice with explicitly hypothetical tax settlements',
        'strategy_backtest': False, 'cash_debits_simulated': False, 'rounding_approved': False,
        'source_url': 'https://static.cninfo.com.cn/finalpage/2025-06-20/1223934491.PDF',
        'source_sha256': PDF_HASH, 'same_source_dual_decoding': verified,
        'hypothetical_settlements': inputs, 'daily_results': results,
        'additional_tax_unrounded': actual, 'independent_rational_check': 'passed'}
    (out / 'result.json').write_text(json.dumps(payload, default=encode, ensure_ascii=False, indent=2), encoding='utf-8')
    sources = [PDF, Path(__file__), ROOT/'src/value_investment_agent/dividend_tax.py',
               ROOT/'src/value_investment_agent/dividend_tax_lots.py']
    manifest = {'inputs': [{'path': str(p), 'sha256': digest(p)} for p in sources],
                'outputs': {'result.json': digest(out/'result.json')}}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(out), 'additional_tax_unrounded': actual,
                      'independent_check': 'passed', 'strategy_backtest': False}, default=encode))


if __name__ == '__main__':
    main()
