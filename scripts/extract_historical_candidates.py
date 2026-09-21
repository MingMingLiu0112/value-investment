"""Extract archived annual candidates outside the production verified-fact pipeline."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from value_investment_agent.filing_extract import extract_candidates, ANNUAL_BACKFILL_PARSER_VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--limit', type=int, default=3)
    parser.add_argument('--output-directory', type=Path)
    args = parser.parse_args()
    if not 1 <= args.limit <= 40:
        parser.error('limit must be 1..40')
    reports = json.loads(args.manifest.read_text(encoding='utf-8'))
    output = args.output_directory or args.manifest.parent / 'candidates' / ANNUAL_BACKFILL_PARSER_VERSION
    output.mkdir(parents=True, exist_ok=True)
    selected = sorted(reports, key=lambda r: (r['announcement_timestamp_raw'], r['symbol']))[:args.limit]
    for report in selected:
        path = Path(report['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != report['sha256']:
            raise ValueError('Archived file hash mismatch')
        packet = extract_candidates(path)
        if packet['sha256'] != report['sha256'] or packet['page_count'] != report['pages']:
            raise ValueError('PDF decoder count or hash mismatch')
        packet.update({'symbol':report['symbol'],'announcement':report,
            'report_period_from_title':re.search(r'20\d{2}',report['title'])[0]+'-12-31',
            'report_period_verified':False,'financial_facts_verified':False,
            'backtest_ready':False})
        target = output / (report['symbol']+'-'+report['announcement_id']+'.json')
        encoded = json.dumps(packet,ensure_ascii=False,sort_keys=True,indent=2).encode('utf-8')
        if target.exists() and target.read_bytes() != encoded:
            raise ValueError('Existing packet differs; retain it and audit parser reproducibility')
        if not target.exists():
            target.write_bytes(encoded)
        print(json.dumps({'symbol':report['symbol'],'title':report['title'],
            'candidate_count':len(packet['candidates']),'fields':sorted({r['field_name'] for r in packet['candidates']}),
            'packet':str(target),'verified':False},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
