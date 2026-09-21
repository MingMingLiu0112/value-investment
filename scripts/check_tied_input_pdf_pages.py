"""Fetch hash-pinned disclosures locally and inspect conflicting input pages."""
import hashlib
import json
from pathlib import Path

import requests
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.filing_extract import extract_candidates_from_pages, ANNUAL_BACKFILL_PARSER_VERSION


REPORTS = [
    ('000612', 'https://static.cninfo.com.cn/finalpage/2026-03-14/1225009217.PDF',
     'ae530051d9ac6d568bb42884d01fb30dcfd04c0cc887725fd594eefcc081ca98', [80, 81, 82, 83]),
    ('002125', 'https://static.cninfo.com.cn/finalpage/2026-04-25/1225191831.PDF',
     '01c39e74315dbc38e3d7d7bf0d12dd439433e7ec2561f45eaadc835e57ec7859', [80, 160, 161]),
    ('300014', 'https://static.cninfo.com.cn/finalpage/2026-03-28/1225045391.PDF',
     '3bee0ca9a6232c60c53f195d078446a45fd4941bd997258b474cebe835eea3b8', [86, 197, 198]),
]
EXPECTED_INPUTS = {
    '000612': ('operating_cost', '5038014974.44', 81),
    '002125': ('bonds_payable', '450138560.42', 80),
    '300014': ('short_term_borrowings', '706335000.01', 86),
}


def main():
    root = Path('runtime/tied-input-original-pages-20260909')
    root.mkdir(exist_ok=True)
    session = requests.Session()
    session.trust_env = False
    regressions = []
    for symbol, url, expected, pages in REPORTS:
        path = root / (symbol + '.pdf')
        if path.exists():
            raw = path.read_bytes()
        else:
            response = session.get(url, timeout=(15, 90))
            response.raise_for_status()
            raw = response.content
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise ValueError('Pinned report hash mismatch: ' + symbol)
        if not path.exists():
            with path.open('xb') as stream:
                stream.write(raw)
        text_pages = extract_pages(path)
        field, expected_value, expected_page = EXPECTED_INPUTS[symbol]
        candidates = [r for r in extract_candidates_from_pages(text_pages) if r['field_name'] == field]
        observed = [(r['value'], r['unit'], r['page']) for r in candidates]
        if observed != [(expected_value, 'CNY', expected_page)]:
            raise ValueError('Original-file candidate regression: ' + symbol + repr(observed))
        regressions.append({'symbol': symbol, 'field': field, 'sha256': actual,
                            'parser_version': ANNUAL_BACKFILL_PARSER_VERSION,
                            'expected_value': expected_value, 'candidates': candidates,
                            'full_document_pages': len(text_pages), 'passed': True})
        result = {'symbol': symbol, 'url': url, 'sha256': actual,
                  'pages': {str(p): text_pages[p - 1] for p in pages},
                  'scope': 'Original page text only; no automatic fact promotion'}
        target = root / (symbol + '-pages.json')
        if not target.exists():
            with target.open('x', encoding='utf-8') as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({'symbol': symbol, 'sha256_matched': True, 'pages': pages}))
    target = root / (ANNUAL_BACKFILL_PARSER_VERSION + '-regression.json')
    with target.open('x', encoding='utf-8') as stream:
        json.dump({'results': regressions, 'production_updated': False,
                   'scope': 'Pinned original-file parser regression, not independent financial verification'},
                  stream, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
