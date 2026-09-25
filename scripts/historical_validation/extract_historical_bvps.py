"""Bounded BVPS research extraction with same-document dual-decoder comparison."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from pypdf import PdfReader
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.historical_bvps import extract_dated_bvps, extract_summary_bvps, extract_dated_share_counts
from value_investment_agent.historical_bvps import extract_linked_bvps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--method', choices=('disclosed', 'summary-derived', 'dated-shares', 'linked-derived'), default='disclosed')
    parser.add_argument('--page-limit', type=int, default=30, choices=range(1, 601), metavar='1-600')
    args = parser.parse_args()
    reports = [r for r in json.loads(args.manifest.read_text(encoding='utf-8'))
               if r['symbol'] == args.symbol]
    if not reports or len(reports) > 40:
        raise ValueError('Expected 1..40 explicitly selected reports')
    rows = []
    for report in reports:
        path = Path(report['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != report['sha256']:
            raise ValueError('Raw file hash mismatch')
        reader = PdfReader(path)
        if len(reader.pages) != report['pages']:
            raise ValueError('Page count mismatch')
        limit = min(args.page_limit, len(reader.pages))
        extractor = {'summary-derived': extract_summary_bvps, 'disclosed': extract_dated_bvps,
                     'dated-shares': extract_dated_share_counts, 'linked-derived': extract_linked_bvps}[args.method]
        first = extractor(extract_pages(path, limit))
        second = extractor([reader.pages[i].extract_text() or '' for i in range(limit)])
        period = re.search(r'20\d{2}', report['title'])[0] + '-12-31'
        def identity(candidates):
            return sorted((r['value'], r['period_label'], r['unit'], r['page']) for r in candidates)
        agrees = bool(first) and identity(first) == identity(second)
        row = {'announcement': report, 'pages_scanned': limit, 'pdfium_candidates': first,
               'pypdf_candidates': second, 'decoder_agreement': agrees,
               'title_period_matches': bool(first) and all(r['period_label'] == period for r in first),
               'independent_source_verified': False, 'backtest_ready': False}
        rows.append(row)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump({'scope': 'Bounded page scan, candidates not approved', 'page_limit': args.page_limit,
                   'method': args.method, 'rows': rows},
                  stream, ensure_ascii=False, indent=2)
    print(json.dumps({'reports': len(rows), 'with_candidates': sum(bool(r['pdfium_candidates']) for r in rows),
                      'decoder_agreement': sum(r['decoder_agreement'] for r in rows),
                      'output': str(args.output)}))


if __name__ == '__main__':
    main()
