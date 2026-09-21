"""Read pinned local notes and reconcile current leases without debt promotion."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import pdfplumber

from value_investment_agent.current_maturities import (
    TITLE, extract_current_maturities, extract_current_maturity_continuation,
    extract_borderless_current_maturities)
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.financing_bridge import bridge_financing_rows, amount


LEASE_LABELS = {'租赁负债(含一年内到期)', '租赁负债(包含一年内到期)',
                '租赁负债(含一年内到期的租赁负债)'}
BORROWING_LABELS = {'长期借款(含一年内到期)', '长期借款(包含一年内到期)',
                    '长期借款(含一年内到期的长期借款)'}


def inspect(path):
    indices = [i for i, text in enumerate(extract_pages(path))
               if any(re.fullmatch(r'\d+[、.．]' + TITLE, ''.join(line.split()))
                      for line in text.splitlines())]
    hits = []
    with pdfplumber.open(path) as document:
        for index in indices:
            page = document.pages[index]
            bottom = 0
            for table in sorted(page.find_tables(), key=lambda t: t.bbox[1]):
                if table.bbox[1] <= bottom:
                    continue
                context = page.crop((0, bottom, page.width, table.bbox[1])).extract_text() or ''
                bottom = table.bbox[3]
                result = extract_current_maturities(table.extract(), context)
                if result is None and table.extract() == [['项目', '期末余额', '期初余额']]:
                    body = page.crop((table.bbox[0], table.bbox[3], table.bbox[2], page.height))
                    result = extract_borderless_current_maturities(
                        table.extract()[0], table.rows[0].cells, body.extract_words(), context)
                if result is None and TITLE in ''.join(context.split()) and index + 1 < len(document.pages):
                    following_page = document.pages[index + 1]
                    following_tables = sorted(following_page.find_tables(), key=lambda t: t.bbox[1])
                    if following_tables:
                        following = following_tables[0]
                        tail = page.crop((0, table.bbox[3], page.width, page.height)).extract_text() or ''
                        prefix = following_page.crop((0, 0, following_page.width, following.bbox[1])).extract_text() or ''
                        result = extract_current_maturity_continuation(
                            table.extract(), following.extract(), context, tail, prefix)
                        if result:
                            result.update(physical_pages=[index + 1, index + 2], continuation_bbox=following.bbox)
                if result:
                    hits.append({**result, 'physical_page': index + 1, 'bbox': table.bbox})
    return hits


def reconcile(source, note, financing, points):
    def bridge(label, value):
        table = {'rows': [{'label': label, 'amounts': {'closing': value}}], 'total': {'unit': 'CNY'}}
        return bridge_financing_rows(table, points, source['symbol'], source['report_period'],
                                     source['sha256'], source['source_url'])
    aggregate = bridge(TITLE, note['total']['amounts']['closing'])
    groups = {}
    specs = [('current_leases', LEASE_LABELS, '租赁负债', 'current_lease_row', 'inclusive_lease_bridges',
              'financing_current_inclusive_leases - current_leases = noncurrent_leases'),
             ('current_borrowings', BORROWING_LABELS, '长期借款', 'current_borrowing_row', 'inclusive_borrowing_bridges',
              'financing_current_inclusive_long_borrowings - current_long_borrowings = noncurrent_long_borrowings')]
    for category, labels, balance_label, row_key, group_key, formula in specs:
        results = []
        current = [r for r in note['rows'] if r['category'] == category]
        if len(current) == 1 and note['reconciliation']['closing'] and aggregate['matched_rows'] == 1:
            current_value = amount(current[0]['amounts']['closing'])
            for row in financing['rows']:
                label = ''.join(row['label'].split()).replace('（', '(').replace('）', ')')
                if label not in labels or current_value is None:
                    continue
                closing = amount(row['amounts']['closing'])
                if closing is None:
                    continue
                result = bridge(balance_label, str(closing - current_value))
                results.append({'financing_row': row, row_key: current[0], 'formula': formula,
                                'derived_noncurrent_cny': str(closing - current_value),
                                'balance_bridge': result, 'complete_debt_verified': False})
        groups[group_key] = results
    return {'aggregate_bridge': aggregate, **groups,
            'complete_debt_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('replay', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = (args.payload, args.manifest, args.replay)
    raw = [path.read_bytes() for path in paths]
    payload, manifest, replay = [json.loads(data) for data in raw]
    rows = []
    for source in manifest['reports']:
        matches = [r for r in replay if r['sha256'] == source['sha256']]
        if len(matches) != 1 or source.get('archive_hash_matched') is not True:
            raise ValueError('Ambiguous or unmatched original')
        original = Path(matches[0]['path'])
        if hashlib.sha256(original.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Original hash changed')
        notes = inspect(original)
        row = {k: source[k] for k in ('symbol', 'source_url', 'sha256', 'report_period')}
        row.update(notes=notes, complete_debt_verified=False)
        financing = [h['parsed'] for h in matches[0]['hits'] if h.get('parsed')]
        if len(notes) == 1 and len(financing) == 1:
            row['reconciliation'] = reconcile(source, notes[0], financing[0],
                payload.get('points', []) + payload.get('annual_points', []))
        rows.append(row)
    output = {'reports': rows, 'scope': 'Local research only; no financial promotion',
              'export_generated_at': payload.get('generated_at'),
              'input_sha256': {str(p): hashlib.sha256(data).hexdigest() for p, data in zip(paths, raw)}}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(output, stream, ensure_ascii=False, indent=2)
    print(json.dumps([{'symbol': r['symbol'], 'notes': len(r['notes']),
        'aggregate_matches': r.get('reconciliation', {}).get('aggregate_bridge', {}).get('matched_rows', 0),
        'lease_matches': sum(b['balance_bridge']['matched_rows'] for b in
                            r.get('reconciliation', {}).get('inclusive_lease_bridges', [])),
        'borrowing_matches': sum(b['balance_bridge']['matched_rows'] for b in
                            r.get('reconciliation', {}).get('inclusive_borrowing_bridges', []))}
        for r in rows], ensure_ascii=False))
