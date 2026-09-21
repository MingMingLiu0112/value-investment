"""Download a bounded set of indexed annual PDFs without promoting financial facts."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from pypdf import PdfReader
from value_investment_agent.disclosures import _download, _sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('index', type=Path)
    parser.add_argument('--per-company', type=int, default=1)
    parser.add_argument('--exact-title', help='Archive this disclosure title instead of annual reports')
    args = parser.parse_args()
    if not 1 <= args.per_company <= 20:
        parser.error('per-company must be 1..20')
    reports = {}
    for path in args.index.glob('*.json'):
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != path.stem.rsplit('-', 1)[-1]:
            raise ValueError('Index hash mismatch')
        archive = json.loads(raw)
        for item in archive['response'].get('announcements') or []:
            title = item.get('announcementTitle', '')
            eligible = (title == args.exact_title if args.exact_title else
                        bool(re.search(r'20\d{2}年?年度报告', title)) and not any(
                            word in title for word in ('摘要', '英文', '取消', '提示', '说明')))
            if not eligible:
                continue
            symbol = str(item['secCode'])
            if symbol not in ('600519', '000333', '601088'):
                raise ValueError('Unexpected issuer')
            reports.setdefault(symbol, {})[str(item['announcementId'])] = (item, path.name)
    root = args.index / 'pdfs'
    root.mkdir(exist_ok=True)
    manifest = []
    for symbol, items in sorted(reports.items()):
        selected = sorted(items.items(), key=lambda pair: (
            pair[1][0]['announcementTime'], pair[0]))[:args.per_company]
        for ident, (item, index_name) in selected:
            if not ident.isdigit():
                raise ValueError('Invalid announcement ID')
            relative = item['adjunctUrl']
            if not re.fullmatch(r'finalpage/[0-9-]+/[0-9]+\.[Pp][Dd][Ff]', relative):
                raise ValueError('Unexpected official PDF path')
            url = 'https://static.cninfo.com.cn/' + relative
            assert urlsplit(url).hostname == 'static.cninfo.com.cn'
            target = root / (symbol + '-' + ident + '.pdf')
            digest = _sha256_file(target) if target.exists() else _download(url, target)
            reader = PdfReader(target)
            if reader.is_encrypted or not len(reader.pages):
                raise ValueError('Unreadable report')
            row = {'symbol':symbol,'announcement_id':ident,'title':item['announcementTitle'],
                'announcement_timestamp_raw':item['announcementTime'],
                'timestamp_precision':'date_only_until_verified','url':url,'sha256':digest,
                'path':str(target),'pages':len(reader.pages),'index_archive':index_name,
                'checked_at':datetime.now(timezone.utc).isoformat(),
                'financial_facts_verified':False,'backtest_ready':False}
            manifest.append(row)
            print(json.dumps(row,ensure_ascii=False),flush=True)
    out = root / ('manifest-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    out.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
