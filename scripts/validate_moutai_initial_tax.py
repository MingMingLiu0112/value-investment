"""Replay disclosed 2015 initial withholding, not final disposal tax or returns."""
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re

from pypdf import PdfReader
import pypdfium2 as pdfium

from value_investment_agent.research_broker import ResearchBroker


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'runtime/historical-filing-index/20260908T062537893160Z/pdfs/600519-1201268407.pdf'
EXPECTED = 'bc57d0f990fbd85a23a9fedb5ee52bf274e8f37ad556dfb4632056e07ae0bd42'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if digest(SOURCE) != EXPECTED:
        raise ValueError('Original source hash mismatch')
    checks = {0: ['600519', '4.37400', '4.15030', '2015年7月17日'],
              1: ['公司暂按5%的税率', '实际每股派发现金红利4.15030元']}
    reader = PdfReader(SOURCE)
    with pdfium.PdfDocument(SOURCE) as doc:
        for index, fragments in checks.items():
            page = doc[index]
            textpage = page.get_textpage()
            texts = [reader.pages[index].extract_text(), textpage.get_text_range()]
            textpage.close()
            page.close()
            for phrase in fragments:
                if any(phrase not in re.sub(r'\s+', '', text) for text in texts):
                    raise ValueError('Disclosed initial withholding text mismatch')
    shares = 100  # Declared hypothetical record-date inventory, not a trade.
    gross = Decimal('4.37400') * shares
    net = Decimal('4.15030') * shares
    initial = gross - net
    if Fraction(initial) != (Fraction(437400, 100000) - Fraction(415030, 100000)) * shares:
        raise ValueError('Independent disclosed-difference check failed')
    broker = ResearchBroker(cash=1000)
    broker.start()
    fundshares = broker.fundshares
    broker.credit_distribution('2015-cash', gross)
    broker.accrue_tax('2015-initial', initial, day=date(2015, 7, 17), evidence_id=EXPECTED)
    before_payment = {'cash': broker.getcash(), 'nav': broker.getvalue()}
    broker.pay_tax('2015-withheld', '2015-initial', initial, day=date(2015, 7, 17))
    expected_cash = float(Decimal('1000') + net)
    if abs(broker.getcash() - expected_cash) > 1e-9 or abs(broker.getvalue() - expected_cash) > 1e-9:
        raise ValueError('Backtrader cash/NAV reconciliation failed')
    if broker.fundshares != fundshares:
        raise ValueError('Tax incorrectly treated as external withdrawal')
    out = ROOT/'runtime/strategy-validation'/('moutai-initial-tax-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    result = {'scope': 'disclosed initial withholding; hypothetical 100 record-date shares',
        'source_url': 'https://static.cninfo.com.cn/finalpage/2015-07-10/1201268407.PDF',
        'original_sha256': EXPECTED, 'same_source_dual_decode': checks,
        'gross_cash': str(gross), 'disclosed_net_cash': str(net),
        'initial_tax': str(initial), 'payment_date': '2015-07-17',
        'before_payment': before_payment, 'after_payment_cash': broker.getcash(),
        'after_payment_nav': broker.getvalue(), 'tax_outstanding': str(broker.tax_liabilities['2015-initial']),
        'fundshares_unchanged': True, 'independent_check': 'passed',
        'bonus_shares_replayed': False, 'final_dividend_tax_approved': False,
        'strategy_backtest': False, 'universal_bonus_tax_base_inferred': False}
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    inputs = [SOURCE, Path(__file__), ROOT/'src/value_investment_agent/research_broker.py']
    manifest = {'inputs': [{'path': str(p), 'sha256': digest(p)} for p in inputs],
                'outputs': {'result.json': digest(out/'result.json')}}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(out), 'initial_tax': str(initial),
                      'cash': broker.getcash(), 'nav': broker.getvalue(), 'verified': True}))


if __name__ == '__main__':
    main()
