"""Compare indicator decoding on archived pages, not independent financial sources."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from pypdf import PdfReader
from value_investment_agent.filing_extract import extract_candidates_from_pages


def compare(packet):
    path = Path(packet['evidence_file'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != packet['sha256']:
        raise ValueError('Archived evidence hash mismatch')
    wanted = [r for r in packet['candidates'] if r['field_name'] in {'eps_annual', 'roe'}]
    reader = PdfReader(path)
    if len(reader.pages) != packet['page_count']:
        raise ValueError('Decoder page count mismatch')
    target_pages = {r['page'] for r in wanted}
    required_pages = set(target_pages)
    for row in wanted:
        if 'header_page' in row:
            header = row['header_page']
            if type(header) is not int or header != row['page'] - 1:
                raise ValueError('Cross-page evidence must reference adjacent header')
            required_pages.add(header)
    texts = [''] * len(reader.pages)
    for page in sorted(required_pages):
        if type(page) is not int or not 1 <= page <= len(reader.pages):
            raise ValueError('Invalid candidate page')
        texts[page - 1] = reader.pages[page - 1].extract_text() or ''
    other = [r for r in extract_candidates_from_pages(texts)
             if r['field_name'] in {'eps_annual', 'roe'} and r['page'] in target_pages]
    def identities(rows):
        return Counter((r['field_name'], r['value'], r['unit'], r['page'],
                        r.get('header_page')) for r in rows)
    expected, actual = identities(wanted), identities(other)
    return {'symbol': packet['symbol'], 'announcement_id': packet['announcement']['announcement_id'],
            'sha256': packet['sha256'], 'pdfium_candidates': wanted,
            'pypdf_candidates': other, 'decoder_agreement': bool(wanted) and expected == actual,
            'comparison_status': ('no_candidates_not_compared' if not wanted else
                                  'matched' if expected == actual else 'decoder_mismatch'),
            'missing_from_pypdf': list((expected - actual).elements()),
            'additional_from_pypdf': list((actual - expected).elements()),
            'independent_source_verified': False, 'backtest_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    packets = [json.loads(p.read_text(encoding='utf-8'))
               for p in sorted(args.directory.glob(args.symbol + '-*.json'))]
    if not packets or any(p['symbol'] != args.symbol for p in packets):
        raise ValueError('No matching packets or issuer mismatch')
    rows = [compare(p) for p in packets]
    result = {'scope': 'Same source and parser, independent PDF decoders only', 'rows': rows}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'reports': len(rows), 'agree': sum(r['decoder_agreement'] for r in rows),
                      'output': str(args.output), 'backtest_ready': False}))


if __name__ == '__main__':
    main()
