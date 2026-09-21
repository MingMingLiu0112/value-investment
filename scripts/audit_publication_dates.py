"""Verify archived index/PDF linkage and derive research date upper bounds."""
import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from value_investment_agent.historical_asof import publication_date_upper_bound


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    reports = json.loads(args.manifest.read_text(encoding='utf-8'))
    if not 1 <= len(reports) <= 40:
        raise ValueError('Expected 1..40 reports')
    rows = []
    for report in reports:
        name = report['index_archive']
        if Path(name).name != name:
            raise ValueError('Unexpected index path')
        index_path = args.manifest.parent.parent / name
        raw_index = index_path.read_bytes()
        digest = hashlib.sha256(raw_index).hexdigest()
        if digest != index_path.stem.rsplit('-', 1)[-1]:
            raise ValueError('Index hash mismatch')
        index = json.loads(raw_index)
        if index['url'] != 'https://www.cninfo.com.cn/new/hisAnnouncement/query':
            raise ValueError('Unexpected index source')
        records = [r for r in index['response']['announcements']
                   if str(r['announcementId']) == str(report['announcement_id'])
                   and r['secCode'] == report['symbol']]
        if len(records) != 1:
            raise ValueError('Announcement identity is missing or ambiguous')
        record = records[0]
        if (record['announcementTime'] != report['announcement_timestamp_raw']
                or record['announcementTitle'] != report['title']
                or 'https://static.cninfo.com.cn/' + record['adjunctUrl'] != report['url']):
            raise ValueError('Manifest and official index disagree')
        if hashlib.sha256(Path(report['path']).read_bytes()).hexdigest() != report['sha256']:
            raise ValueError('PDF hash mismatch')
        stamp = record['announcementTime']
        if type(stamp) is not int:
            raise ValueError('Unexpected official date encoding')
        day = datetime.fromtimestamp(stamp / 1000, timezone(timedelta(hours=8))).date().isoformat()
        if urlparse(report['url']).path.split('/')[2] != day:
            raise ValueError('Index date and official PDF path date disagree')
        rows.append({'symbol': report['symbol'], 'announcement_id': report['announcement_id'],
                     'title': report['title'], 'published_date': day,
                     'research_not_before': publication_date_upper_bound(day).isoformat(),
                     'timestamp_precision': 'date', 'intraday_time_verified': False,
                     'date_source_consistency_verified': True,
                     'availability_method': 'china_publication_date_upper_bound',
                     'source_url': report['url'], 'raw_file_hash': report['sha256'],
                     'index_path': str(index_path), 'index_hash': digest,
                     'financial_facts_verified': False, 'backtest_ready': False})
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump({'scope': 'Same-source publication date consistency, not independent availability proof',
                   'rows': rows}, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'reports': len(rows), 'date_consistent': len(rows), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
