"""Archive official IPO evidence separately from statutory annual report facts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from value_investment_agent.db import connect, begin_run, end_run
from value_investment_agent.disclosures import _request_json, _download, _sha256_file, _is_complete_pdf
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.settings import get_settings

settings = get_settings()
if settings.evidence_directory != Path('/app/evidence'):
    raise ValueError('Set EVIDENCE_DIRECTORY=/app/evidence and mount the persistent evidence directory')
for symbol, org in [('001237','9900063097'), ('920079','gfbj0874075'), ('920138','9900034944')]:
    with connect(settings.database_url) as db:
        run = begin_run(db, 'archive-ipo-evidence')
    documents = []
    try:
        for keyword, kind in [('招股说明书', 'prospectus'), ('上市公告书', 'listing_notice')]:
            payload = _request_json({'pageNum':'1','pageSize':'30','tabName':'fulltext','column':'',
                'stock':f'{symbol},{org}','searchkey':keyword,'secid':'','plate':'','category':'',
                'trade':'','seDate':'','sortName':'','sortType':'','isHLtitle':'false'})
            matches = [r for r in payload.get('announcements') or []
                       if str(r.get('secCode')) == symbol and r.get('adjunctUrl')
                       and str(r.get('announcementTitle', '')).endswith(keyword)]
            if not matches:
                raise ValueError(f'No exact-code full {kind} for {symbol}')
            announcement = max(matches, key=lambda r: int(r['announcementTime']))
            url = 'https://static.cninfo.com.cn/' + announcement['adjunctUrl'].lstrip('/')
            key = hashlib.sha256(url.encode()).hexdigest()
            path = settings.evidence_directory / symbol / f'{kind}-{key}.pdf'
            digest = _sha256_file(path) if _is_complete_pdf(path) else _download(url, path)
            if not _is_complete_pdf(path):
                raise ValueError(f'Non-PDF response: {url}')
            pages = extract_pages(path, limit=20)
            relevant = [{'page': index, 'excerpt': page[:3500]} for index, page in enumerate(pages, 1)
                        if ('上市日期' in page or '上市时间' in page or '报告期' in page)]
            documents.append({'symbol': symbol, 'document_kind': kind, 'source_url': url,
                'title': announcement['announcementTitle'], 'sha256': digest, 'local_path': str(path),
                'published_at': datetime.fromtimestamp(int(announcement['announcementTime'])/1000, timezone.utc).isoformat(),
                'fetched_at': datetime.now(timezone.utc).isoformat(), 'pages_inspected': len(pages),
                'research_excerpts': relevant[:4], 'financial_facts_promoted': False})
        status, error = 'succeeded', None
    except Exception as exception:
        status, error = 'failed', str(exception)
    with connect(settings.database_url) as db:
        end_run(db, run, status, {'symbol': symbol, 'documents': documents, 'error': error})
    print(json.dumps({'symbol': symbol, 'status': status, 'error': error,
        'documents': [{k: v for k, v in d.items() if k != 'research_excerpts'} for d in documents]}, ensure_ascii=False), flush=True)
