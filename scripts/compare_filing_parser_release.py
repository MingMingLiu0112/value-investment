"""Compare all candidate facts on retained PDFs; never approve or promote facts."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

from value_investment_agent import filing_extract, combined_balance
from value_investment_agent.pdf_text import extract_pages

BASELINE_SHA256 = '0dcb08573a48a2063997317a3354c13f23b68497644c4b39cb5c21e27d0fa99b'


def retained_entries(source):
    if source.is_dir():
        for packet_path in sorted(source.glob('*.json')):
            packet = json.loads(packet_path.read_text(encoding='utf-8'))
            original = packet['announcement']
            yield {'symbol': packet['symbol'], 'period': packet['report_period_from_title'],
                   'official_sha256': original['sha256'], 'path': original['path']}
    else:
        packet = json.loads(source.read_text(encoding='utf-8'))
        for entry in packet['results']:
            yield {**entry, 'path': str(source.parent / (entry['symbol'] + '.pdf'))}


def compare(before, after):
    fields = ('field_name', 'value', 'unit', 'page')
    def counts(rows):
        return Counter(tuple(str(row[key]) for key in fields) for row in rows)
    def expand(values):
        return [{**dict(zip(fields, key)), 'count': count}
                for key, count in sorted(values.items())]
    old, new = counts(before), counts(after)
    grouped = defaultdict(set)
    for row in after:
        grouped[row['field_name']].add((str(row['value']), row['unit']))
    return {'added': expand(new - old), 'removed': expand(old - new),
            'duplicate_facts': expand(Counter({k: v for k, v in new.items() if v > 1})),
            'multiple_values': {k: sorted(v) for k, v in grouped.items() if len(v) > 1}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('manifests', type=Path, nargs='+')
    parser.add_argument('--baseline-sha256', default=BASELINE_SHA256)
    args = parser.parse_args()
    if hashlib.sha256(args.baseline.read_bytes()).hexdigest() != args.baseline_sha256:
        raise ValueError('Downloaded production baseline hash changed')
    spec = importlib.util.spec_from_file_location('reviewed_production_parser', args.baseline)
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    results = []
    for manifest in args.manifests:
        for entry in retained_entries(manifest):
            path = Path(entry['path'])
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry['official_sha256']:
                raise ValueError('Original hash mismatch: ' + str(path))
            pages = extract_pages(path)
            old = baseline.extract_candidates_from_pages(pages)
            new = filing_extract.extract_candidates_from_pages(pages)
            result = {'symbol': entry['symbol'], 'period': entry['period'],
                      'source_manifest': str(manifest), 'pdf_sha256': entry['official_sha256'],
                      'before_count': len(old), 'after_count': len(new), **compare(old, new)}
            results.append(result)
            print(json.dumps({'symbol': entry['symbol'], 'added': len(result['added']),
                              'removed': len(result['removed']),
                              'multiple_value_fields': list(result['multiple_values'])}), flush=True)
    output = {'baseline_sha256': args.baseline_sha256,
              'release_files': {module.__name__: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                                for module in (filing_extract, combined_balance)},
              'parser_version': filing_extract.ANNUAL_BACKFILL_PARSER_VERSION,
              'results': results, 'production_updated': False, 'release_approved': False,
              'scope': 'Candidate differences only; new and removed facts require source review'}
    target = Path('runtime/income-gap-crosschecks') / ('release-diff-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(output, stream, ensure_ascii=False, indent=2)
    print(str(target))


if __name__ == '__main__':
    main()
