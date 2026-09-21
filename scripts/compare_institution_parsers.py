"""Compare a retained deployed parser with current code on explicit local PDFs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from pypdf import PdfReader
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.institution_metrics import parse_tables, VERSION


def signature(fact):
    return {key: fact.get(key) for key in
            ('value', 'unit', 'statement_scope', 'capital_method', 'period_basis')}


def compare(before, after):
    old = {f['field_name']: f for f in before}
    new = {f['field_name']: f for f in after}
    return {'added': sorted(new.keys() - old.keys()), 'removed': sorted(old.keys() - new.keys()),
            'changed': {k: {'before': signature(old[k]), 'after': signature(new[k])}
                        for k in old.keys() & new.keys() if signature(old[k]) != signature(new[k])}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--report', nargs=4, action='append', required=True,
                        metavar=('SYMBOL', 'MODEL', 'PERIOD', 'PDF'))
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('retained_institution_parser', args.baseline)
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    rows = []
    for symbol, model, period, filename in args.report:
        path = Path(filename)
        pages = extract_pages(path)
        fallback = [p.extract_text() or '' for p in PdfReader(path).pages]
        before = baseline.parse_tables(pages, model, period, fallback_pages=fallback)
        after = parse_tables(pages, model, period, fallback_pages=fallback)
        row = {'symbol': symbol, 'period': period, 'pdf': str(path),
               'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
               **compare(before, after), 'before': before, 'after': after}
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k not in ('before', 'after')}, ensure_ascii=False), flush=True)
    args.output.write_text(json.dumps({'baseline_version': baseline.VERSION, 'current_version': VERSION,
        'baseline_sha256': hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        'independent_source_verification': False, 'reports': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
