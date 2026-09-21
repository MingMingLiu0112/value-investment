"""Archive pinned original pages for unresolved brokerage cash definitions."""
import hashlib
import json
from pathlib import Path

import requests
from value_investment_agent.pdf_text import extract_pages


def main():
    payload = json.loads(Path('runtime/server-export-payload.json').read_text(encoding='utf-8'))
    targets = {'601555': [102, 103, 194, 195, 202, 203],
               '601688': [312, 313, 346, 347]}
    root = Path('runtime/broker-cash-conflicts-20260909')
    root.mkdir(exist_ok=True)
    session = requests.Session()
    session.trust_env = False
    for symbol, page_numbers in targets.items():
        point = next(p for p in payload['annual_points'] if p['symbol'] == symbol and p['field_name'] == 'cash')
        path = root / (symbol + '.pdf')
        if path.exists():
            raw = path.read_bytes()
        else:
            response = session.get(point['source_url'], timeout=(15, 90))
            response.raise_for_status()
            raw = response.content
        if hashlib.sha256(raw).hexdigest() != point['sha256']:
            raise ValueError('Pinned original changed: ' + symbol)
        if not path.exists():
            with path.open('xb') as stream:
                stream.write(raw)
        pages = extract_pages(path, max(page_numbers))
        result = {'symbol': symbol, 'source_url': point['source_url'], 'sha256': point['sha256'],
                  'pages': {str(p): pages[p-1] for p in page_numbers},
                  'production_updated': False}
        target = root / (symbol + '-pages.json')
        with target.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({'symbol': symbol, 'hash_verified': True, 'pages': page_numbers}))


if __name__ == '__main__':
    main()
