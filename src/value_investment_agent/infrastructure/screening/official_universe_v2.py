"""Versioned official-list acquisition; the legacy v1 collector stays unchanged."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests

from ...official_universe import (
    SZSE_URL, SSE_URL, BSE_URL, parse_szse, parse_sse, parse_bse_page, _code, _date, _unique,
)
from ...domain.discovery.official_list_calendar import completed_list_session, validate_list_timing

VERSION = 'official-security-lists-v2-session-date'


def replay_official_documents(documents, *, started_at, available_at):
    """Reparse exact bytes and complete pages; acquisition times are never restamped."""
    by_label = {}
    for doc in documents:
        if doc['label'] in by_label or sha256(doc['raw']).hexdigest() != doc['sha256']:
            raise ValueError('Duplicate official document or raw hash mismatch')
        by_label[doc['label']] = doc
    szse = parse_szse(by_label['SZSE_A']['raw'])
    sse = parse_sse(by_label['SSE_1']['raw'], '主板') + parse_sse(by_label['SSE_8']['raw'], '科创板')
    first = parse_bse_page(by_label['BSE_0']['raw'])
    total, pages = int(first['totalElements']), int(first['totalPages'])
    if not 1 <= pages <= 200:
        raise ValueError('BSE pagination bounds invalid')
    if set(by_label) != {'SZSE_A', 'SSE_1', 'SSE_8', *(f'BSE_{i}' for i in range(pages))}:
        raise ValueError('Official pages missing or unexpected')
    bse = []
    for index in range(pages):
        page = parse_bse_page(by_label[f'BSE_{index}']['raw'])
        if (int(page['totalElements']), int(page['totalPages']), int(page['number'])) != (total, pages, index):
            raise ValueError('BSE totals or page sequence changed')
        for row in page['content']:
            bse.append(dict(symbol=_code(row['xxzqdm']), name=row['xxzqjc'], board='北交所', exchange='BSE',
                listed_on=_date(row['fxssrq']), as_of=_date(row['xxjsrq']),
                listing_date_basis='精选层平移公司此日期为精选层挂牌日期；其他为本所上市日期',
                security_type='A股', official_industry=row.get('xxhyzl')))
    if len(bse) != total:
        raise ValueError('BSE final count mismatch')
    records = _unique(szse + sse + bse)
    if len(szse) < 2000 or len(sse) < 2000 or len(bse) < 200:
        raise ValueError('Exchange universe unexpectedly small; refuse coverage claim')
    timing = validate_list_timing(provider_dates=[r['as_of'] for r in bse],
        fetched_at=[doc['fetched_at'] for doc in documents], started_at=started_at, available_at=available_at)
    if any(row['listed_on'] > timing['effective_session'] for row in records):
        raise ValueError('Official list contains future listing dates relative to effective session')
    return dict(parser_version=VERSION, records=records,
        sources=[{k: v for k, v in doc.items() if k != 'raw'} for doc in documents],
        fetched_at=available_at.isoformat(), available_at=available_at.isoformat(),
        effective_session=timing['effective_session'], collection_timing=timing,
        exchange_counts=dict(Counter(r['exchange'] for r in records)),
        board_counts=dict(Counter(r['board'] for r in records)),
        scope='沪深A股、科创板境内存托凭证、北交所股票', complete=True)


def collect_security_lists_v2(directory: Path, *, clock=None):
    """Free official requests only; always archive raw bytes at the actual clock."""
    import shutil
    clock = clock or (lambda: datetime.now(timezone.utc))
    started = clock()
    completed_list_session(started)  # fail before HTTP on uncovered or incomplete sessions
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    documents = []
    with requests.Session() as session:
        session.trust_env = False

        def fetch(label, url, *, params=None, data=None, referer=None):
            headers = {'User-Agent': 'Mozilla/5.0'}
            if referer:
                headers['Referer'] = referer
            if params:
                url += '?' + urlencode(params)
            body = urlencode(data).encode() if data is not None else None
            if body:
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
            with session.request('POST' if body else 'GET', url, data=body, headers=headers,
                                 timeout=(15, 30), stream=True, allow_redirects=False) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError('Official exchange response must be HTTP 200, no redirects: '
                                     f'{label} HTTP {response.status_code}')
                raw = bytearray()
                for chunk in response.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw) > 8 * 1024**2:
                        raise ValueError('Exchange response exceeds bounded archive size')
                raw = bytes(raw)
                final_url = response.url
                if (urlparse(final_url).scheme != 'https'
                        or urlparse(final_url).hostname != urlparse(url).hostname):
                    raise ValueError('Official response redirected outside its source host')
            digest = sha256(raw).hexdigest()
            path = directory / (digest + '.bin')
            if path.exists():
                if sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError('Retained exchange response hash mismatch')
            else:
                if shutil.disk_usage(directory).free - len(raw) < 2 * 1024**3:
                    raise OSError('Preserve 2 GiB database disk reserve')
                partial = path.with_suffix('.part')
                with partial.open('xb') as stream:
                    stream.write(raw)
                partial.replace(path)
            documents.append(dict(label=label, url=final_url, request_url=url, request_data=data,
                sha256=digest, local_path=str(path), fetched_at=clock().isoformat(), raw=raw))
            return raw

        fetch('SZSE_A', SZSE_URL, params={'SHOWTYPE': 'xlsx', 'CATALOGID': '1110', 'TABKEY': 'tab1'})
        for kind in ('1', '8'):
            fetch('SSE_' + kind, SSE_URL, params=dict(STOCK_TYPE=kind,
                sqlId='COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L', COMPANY_STATUS='2,4,5,7,8',
                type='inParams', isPagination='true', **{'pageHelp.pageSize': '10000',
                'pageHelp.pageNo': '1', 'pageHelp.beginPage': '1', 'pageHelp.endPage': '1'}),
                referer='https://www.sse.com.cn/assortment/stock/list/share/')
        index, pages, declared = 0, 1, None
        while index < pages:
            page = parse_bse_page(fetch('BSE_' + str(index), BSE_URL, data={
                'page': str(index), 'typejb': 'T', 'xxfcbj[]': '2', 'xxzqdm': '',
                'sortfield': 'xxzqdm', 'sorttype': 'asc'}))
            actual = (int(page['totalElements']), int(page['totalPages']))
            if (declared is not None and actual != declared) or int(page['number']) != index:
                raise ValueError('BSE totals or pagination changed during collection')
            declared = actual
            pages = actual[1]
            if not 1 <= pages <= 200:
                raise ValueError('BSE pagination bounds invalid')
            index += 1
    return replay_official_documents(documents, started_at=started, available_at=clock())
