"""Read-only, bounded text diagnostics for a retained official annual report."""
import argparse
import hashlib
import json
from pathlib import Path

from value_investment_agent.db import connect
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.settings import get_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('symbol')
    parser.add_argument('--start-page', type=int, default=1)
    parser.add_argument('--period')
    parser.add_argument('--term')
    parser.add_argument('--engine', choices=['pdfium', 'pypdf', 'dual'], default='pdfium')
    parser.add_argument('--model', choices=['bank', 'broker', 'insurer'])
    args = parser.parse_args()
    if args.start_page < 1:
        parser.error('start-page must be positive')
    if args.engine == 'dual' and not args.model:
        parser.error('dual requires an institution model')
    if len(args.symbol) != 6 or not args.symbol.isascii() or not args.symbol.isdigit():
        parser.error('Expected a six-digit symbol')
    with connect(get_settings().database_url) as db:
        db.execute('SET TRANSACTION READ ONLY')
        report = db.execute("""SELECT symbol,report_period,source_url,sha256,local_path
            FROM official_disclosures WHERE symbol=%s
              AND ((%s::text IS NULL AND report_kind='annual') OR report_period=%s)
            ORDER BY report_period DESC,published_at DESC LIMIT 1""",
            (args.symbol,args.period,args.period)).fetchone()
    if not report:
        raise SystemExit('No retained annual report')
    path = Path(report['local_path'])
    with path.open('rb') as handle:
        if hashlib.file_digest(handle, 'sha256').hexdigest() != report['sha256']:
            raise ValueError('Retained report hash mismatch')
    if args.engine == 'dual':
        from pypdf import PdfReader
        from institution_metrics import parse_tables
        primary = extract_pages(path)
        secondary = [page.extract_text() or '' for page in PdfReader(path).pages]
        facts = parse_tables(primary, args.model, report['report_period'], fallback_pages=secondary)
        print(json.dumps({**report, 'facts': facts, 'read_only': True}, ensure_ascii=False))
        return
    if args.engine == 'pypdf':
        from pypdf import PdfReader
        pages = [page.extract_text() or '' for page in PdfReader(path).pages]
    else:
        pages = extract_pages(path)
    terms = ['\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868', '\u8425\u4e1a\u6536\u5165',
             '\u8d22\u52a1\u62a5\u544a', '\u5229\u6da6\u8868']
    if args.term:
        terms = [args.term]
    matches = []
    for number, page in enumerate(pages, 1):
        if number >= args.start_page and any(term in page for term in terms):
            matches.append({'page': number, 'text': page[:4500]})
    print(json.dumps({**report, 'pages': len(pages), 'characters': sum(map(len, pages)),
                     'first_page': pages[0][:1500] if pages else '',
                     'matched_page_count': len(matches), 'matches': matches[:12]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
