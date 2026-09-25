"""Retain body-date candidates and conflicting revisions outside production."""
import argparse
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader
from value_investment_agent.corporate_actions import (
    distribution_title_status, extract_distribution_dates,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    reports = {}
    for path in args.directory.glob('manifest-*.json'):
        for report in json.loads(path.read_text(encoding='utf-8')):
            key = report['announcement_id']
            if key in reports and reports[key]['sha256'] != report['sha256']:
                raise ValueError('Conflicting raw versions under same announcement ID')
            reports[key] = report
    packets = []
    for report in reports.values():
        path = Path(report['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != report['sha256']:
            raise ValueError('Raw PDF hash mismatch')
        pages = [p.extract_text() or '' for p in PdfReader(path).pages]
        rows = extract_distribution_dates(pages)
        fields = {r['field'] for r in rows}
        conflicts = {f: sorted({r['value'] for r in rows if r['field'] == f}) for f in fields}
        packets.append({'announcement': report, 'title_status': distribution_title_status(report['title']),
                        'candidates': rows, 'conflicts': {k: v for k, v in conflicts.items() if len(v) > 1},
                        'backtest_ready': False})
    target = args.directory / 'date-candidates-v2.json'
    target.write_text(json.dumps({'parser_version': 'distribution-dates-v2-exact-table', 'packets': packets},
                                ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'documents': len(packets), 'date_candidates': sum(len(p['candidates']) for p in packets),
                      'documents_with_dates': sum(bool(p['candidates']) for p in packets),
                      'documents_with_conflicts': sum(bool(p['conflicts']) for p in packets),
                      'path': str(target)}))


if __name__ == '__main__':
    main()
