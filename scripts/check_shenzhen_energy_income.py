"""Replay a pinned interim report for a missing attributable-profit candidate."""
import hashlib
import json
from pathlib import Path

import requests
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.filing_extract import extract_candidates_from_pages, ANNUAL_BACKFILL_PARSER_VERSION


def main():
    url = 'https://static.cninfo.com.cn/finalpage/2026-08-26/1225503660.PDF'
    expected = '181663cbf6a61cd35a5d3b87d3eaa2d2ee7810db0d76bb051eae3d4a2206f29e'
    root = Path('runtime/shenzhen-energy-income-20260909')
    root.mkdir(exist_ok=True)
    path = root / '000027-2026H1.pdf'
    session = requests.Session()
    session.trust_env = False
    if path.exists():
        raw = path.read_bytes()
    else:
        response = session.get(url, timeout=(15, 90))
        response.raise_for_status()
        raw = response.content
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Original report hash changed')
    if not path.exists():
        with path.open('xb') as stream:
            stream.write(raw)
    pages = extract_pages(path)
    candidates = [c for c in extract_candidates_from_pages(pages)
                  if c['field_name'] in ('net_income', 'operating_cash_flow')]
    result = {'source_url': url, 'sha256': expected, 'parser': ANNUAL_BACKFILL_PARSER_VERSION,
              'candidates': candidates, 'production_updated': False,
              'income_pages': {str(i+1): text for i, text in enumerate(pages)
                               if '1,902,740,083.22' in text or '归属于母公司股东的净利润' in text}}
    with (root / 'replay.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(candidates, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
