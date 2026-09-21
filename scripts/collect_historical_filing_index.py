"""Archive bounded official annual indexes, preserving all announcement versions."""
import hashlib
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from value_investment_agent.disclosures import (
    _request_json, _cninfo_security_id, _discover_security_id, SEARCH_URL,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--company', nargs=2, action='append', metavar=('CODE', 'NAME'))
    parser.add_argument('--search-key', default='')
    parser.add_argument('--category', default='category_ndbg_szsh')
    parser.add_argument('--all-categories', action='store_true')
    parser.add_argument('--start', default='2015-01-01')
    parser.add_argument('--end', default='2025-12-31')
    args = parser.parse_args()
    companies = args.company or [('600519','贵州茅台'),('000333','美的集团'),('601088','中国神华')]
    if len(companies) > 10 or any(len(s) != 6 or not s.isascii() or not s.isdigit() for s, _ in companies):
        parser.error('Provide at most ten six-digit company codes')
    start, end = datetime.fromisoformat(args.start), datetime.fromisoformat(args.end)
    if start > end:
        parser.error('Start date is after end date')
    root = Path('runtime/historical-filing-index') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    root.mkdir(parents=True, exist_ok=False)
    for symbol, name in companies:
        column, fallback = _cninfo_security_id(symbol)
        org = _discover_security_id(symbol, column, fallback, name)
        items = []
        expected = None
        for page in range(1, 21):
            query = {'pageNum':str(page),'pageSize':'30','tabName':'fulltext',
                'column':column,'stock':symbol+','+org,'searchkey':args.search_key,'secid':'','plate':'',
                'category':'' if args.all_categories else args.category,'trade':'','seDate':args.start+'~'+args.end,
                'sortName':'','sortType':'','isHLtitle':'false'}
            response = _request_json(query)
            archive = {'url':SEARCH_URL,'query':query,'fetched_at':datetime.now(timezone.utc).isoformat(),
                       'response':response,'timestamp_precision':'announcement_date_not_intraday_verified'}
            content = json.dumps(archive,ensure_ascii=False,sort_keys=True).encode('utf-8')
            digest = hashlib.sha256(content).hexdigest()
            (root / (symbol+'-'+str(page)+'-'+digest+'.json')).write_bytes(content)
            total = int(response['totalAnnouncement'])
            if expected is not None and total != expected:
                raise ValueError('Pagination total changed for '+symbol)
            expected = total
            batch = response.get('announcements') or []
            if any(str(x.get('secCode')) != symbol for x in batch):
                raise ValueError('Wrong issuer in response')
            items.extend(batch)
            if not response.get('hasMore'):
                break
            if not batch:
                raise ValueError('Empty intermediate page')
        else:
            raise ValueError('Page bound exceeded')
        ids = {x.get('announcementId') for x in items}
        if len(items) != expected or len(ids) != expected or None in ids:
            raise ValueError('Incomplete or duplicate announcement index')
        print(json.dumps({'symbol':symbol,'announcements':len(items),'index_complete':True,
            'directory':str(root),'pdfs_downloaded':False,'backtest_ready':False,
            'titles':[x.get('announcementTitle') for x in items]},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
