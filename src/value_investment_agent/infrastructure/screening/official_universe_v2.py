"""Versioned official-list acquisition; the legacy v1 collector stays unchanged."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from ...official_universe import (
    SZSE_URL, SSE_URL, BSE_URL, parse_szse, parse_sse, parse_bse_page, _code, _date, _unique,
)
from ...domain.discovery.official_list_calendar import aware, completed_list_session, validate_list_timing

VERSION = 'official-security-lists-v2-session-date'
PARTIAL_VERSION = 'official-security-lists-partial-v1'
VENUE_LABELS = {'SZSE': ('SZSE_A',), 'SSE': ('SSE_1', 'SSE_8'), 'BSE': ('BSE_0',)}


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
        # Respect the operator's existing proxy/CA environment; never force a
        # separate direct route or follow a challenge/redirect to recover data.
        session.trust_env = True

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
                                 timeout=(15, 30), stream=True, allow_redirects=False, verify=True) as response:
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


def _coverage_request_identity(label, reference):
    """Bind each retained label to the exact requested board/page, not just host."""
    if label == 'SZSE_A':
        endpoint, data = SZSE_URL, None
        params = {'SHOWTYPE': 'xlsx', 'CATALOGID': '1110', 'TABKEY': 'tab1'}
    elif label in {'SSE_1', 'SSE_8'}:
        endpoint, data = SSE_URL, None
        params = dict(STOCK_TYPE=label[-1], sqlId='COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L',
            COMPANY_STATUS='2,4,5,7,8', type='inParams', isPagination='true',
            **{'pageHelp.pageSize': '10000', 'pageHelp.pageNo': '1',
               'pageHelp.beginPage': '1', 'pageHelp.endPage': '1'})
    else:
        endpoint, params = BSE_URL, {}
        data = {'page': label[4:], 'typejb': 'T', 'xxfcbj[]': '2', 'xxzqdm': '',
                'sortfield': 'xxzqdm', 'sorttype': 'asc'}
    url = urlparse(reference['request_url'])
    if (url._replace(query='', fragment='').geturl() != endpoint or url.fragment
            or parse_qs(url.query, keep_blank_values=True) != {k: [v] for k, v in params.items()}
            or reference['request_data'] != data):
        raise ValueError('Official request board/page identity mismatch')


def replay_official_venue_coverage(documents, *, request_failures, started_at, available_at):
    """Rebuild observed venue coverage, never substitute missing venues or dates.

    All-success returns the original full V2 contract. Partial has its own
    version and is not eligible for an unscoped full-market consumer.
    """
    start, finish = aware(started_at), aware(available_at)
    session = completed_list_session(available_at)
    if start > finish or start.date() != finish.date() or completed_list_session(started_at) != session:
        raise ValueError('Official collection crossed dates or session boundaries')
    by_label = {}
    for doc in documents:
        label = doc['label']
        if (label in by_label or sha256(doc['raw']).hexdigest() != doc['sha256']
                or not (label in {'SZSE_A', 'SSE_1', 'SSE_8'}
                        or label.startswith('BSE_') and label[4:].isdigit() and 0 <= int(label[4:]) < 200)):
            raise ValueError('Duplicate, unknown or hash-mismatched official response')
        stamp = aware(datetime.fromisoformat(doc['fetched_at']))
        if not start <= stamp <= finish:
            raise ValueError('Official response outside acquisition interval')
        expected_url = SZSE_URL if label == 'SZSE_A' else SSE_URL if label.startswith('SSE_') else BSE_URL
        if (doc['request_url'].split('?', 1)[0] != expected_url
                or urlparse(doc['url']).scheme != 'https'
                or urlparse(doc['url']).hostname != urlparse(expected_url).hostname
                or urlparse(doc['url']).path != urlparse(expected_url).path
                or urlparse(doc['url']).fragment
                or parse_qs(urlparse(doc['url']).query, keep_blank_values=True)
                    != parse_qs(urlparse(doc['request_url']).query, keep_blank_values=True)
                or type(doc['http_status']) is not int):
            raise ValueError('Official response source identity mismatch')
        _coverage_request_identity(label, doc)
        by_label[label] = doc
    failures = []
    seen_failures = set()
    for failure in request_failures:
        label = failure['label']
        if label in seen_failures or label in by_label or label not in {
                'SZSE_A', 'SSE_1', 'SSE_8', *(f'BSE_{i}' for i in range(200))}:
            raise ValueError('Invalid or conflicting official request failure')
        stamp = aware(datetime.fromisoformat(failure['observed_at']))
        if not start <= stamp <= finish:
            raise ValueError('Official request failure outside acquisition interval')
        _coverage_request_identity(label, failure)
        if not all(isinstance(failure.get(key), str) and failure[key] for key in ('reason', 'error_type')):
            raise ValueError('Invalid official request failure description')
        seen_failures.add(label)
        failures.append(dict(failure))
    coverage, records = {}, []
    for venue, expected in VENUE_LABELS.items():
        selected = {k: v for k, v in by_label.items()
                    if k in expected or venue == 'BSE' and k.startswith('BSE_')}
        errors = [dict(f) for f in failures if f['label'] in expected
                  or venue == 'BSE' and f['label'].startswith('BSE_')]
        rows = []
        try:
            if errors or not set(expected) <= set(selected):
                raise ValueError('Missing official venue responses')
            for doc in selected.values():
                if doc['http_status'] != 200:
                    raise ValueError(f"{doc['label']} HTTP {doc['http_status']}")
            if venue == 'SZSE':
                rows = parse_szse(selected['SZSE_A']['raw'])
            elif venue == 'SSE':
                rows = parse_sse(selected['SSE_1']['raw'], '主板') + parse_sse(selected['SSE_8']['raw'], '科创板')
            else:
                first = parse_bse_page(selected['BSE_0']['raw'])
                total, pages = int(first['totalElements']), int(first['totalPages'])
                if not 1 <= pages <= 200 or set(selected) != {f'BSE_{i}' for i in range(pages)}:
                    raise ValueError('BSE pages missing or unexpected')
                for index in range(pages):
                    page = parse_bse_page(selected[f'BSE_{index}']['raw'])
                    if (int(page['totalElements']), int(page['totalPages']), int(page['number'])) != (total, pages, index):
                        raise ValueError('BSE totals or page sequence changed')
                    rows.extend(dict(symbol=_code(r['xxzqdm']), name=r['xxzqjc'], board='北交所', exchange='BSE',
                        listed_on=_date(r['fxssrq']), as_of=_date(r['xxjsrq']),
                        listing_date_basis='精选层平移公司此日期为精选层挂牌日期；其他为本所上市日期',
                        security_type='A股', official_industry=r.get('xxhyzl')) for r in page['content'])
                if len(rows) != total:
                    raise ValueError('BSE final count mismatch')
                validate_list_timing(provider_dates=[r['as_of'] for r in rows],
                    fetched_at=[d['fetched_at'] for d in selected.values()],
                    started_at=started_at, available_at=available_at)
            _unique(rows)
            if len(rows) < (200 if venue == 'BSE' else 2000):
                raise ValueError('Exchange universe unexpectedly small; refuse coverage claim')
            if any(row['listed_on'] > session.isoformat() or row['exchange'] != venue for row in rows):
                raise ValueError('Official venue identity or listing date mismatch')
        except Exception as error:
            # Parsing is venue-local; ZIP/XML/JSON/schema errors must not erase
            # another venue. Raw identity, hash and clock checks above still fail closed.
            rows = []
            errors.append(dict(error_type=type(error).__name__, reason=str(error)))
        coverage[venue] = dict(status='FAILED' if errors else 'COMPLETE', complete=not errors,
            record_count=None if errors else len(rows), source_labels=sorted(selected), failures=errors,
            source_bindings=[{k: value for k, value in doc.items() if k != 'raw'}
                             for doc in selected.values()],
            provider_date_observed=venue == 'BSE' and not errors)
        records.extend(rows)
    _unique(records)
    covered = [v for v in VENUE_LABELS if coverage[v]['complete']]
    if len(covered) == len(VENUE_LABELS):
        return replay_official_documents(documents, started_at=started_at, available_at=available_at)
    return dict(parser_version=PARTIAL_VERSION, action='no_order', complete=False,
        status='PARTIAL' if covered else 'UNAVAILABLE', scope='OBSERVED_VENUES_ONLY_NOT_ALL_A',
        required_venues=list(VENUE_LABELS), covered_venues=covered,
        failed_venues=[v for v in VENUE_LABELS if v not in covered], venue_coverage=coverage,
        missing_venues=[v for v in VENUE_LABELS if v not in covered],
        records=records, sources=[{k: v for k, v in doc.items() if k != 'raw'} for doc in documents],
        request_failures=failures, fetched_at=available_at.isoformat(), available_at=available_at.isoformat(),
        effective_session=session.isoformat(), exchange_counts=dict(Counter(r['exchange'] for r in records)),
        board_counts=dict(Counter(r['board'] for r in records)),
        collection_timing=dict(collection_started_at=started_at.isoformat(),
            available_at=available_at.isoformat(), effective_session=session.isoformat(),
            provider_date_scope='BSE_ONLY_WHEN_COMPLETE_SSE_SZSE_RESPONSES_UNDATED',
            quote_date_verified=False, strict_contemporaneous_pit=False))


def collect_security_lists_with_coverage(directory: Path, *, clock=None):
    """Explicit opt-in acquisition that preserves independent venue responses."""
    import shutil
    clock = clock or (lambda: datetime.now(timezone.utc))
    started = clock()
    completed_list_session(started)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    documents, failures = [], []
    with requests.Session() as session:
        session.trust_env = True

        def fetch(label, url, *, params=None, data=None, referer=None):
            if params:
                url += '?' + urlencode(params)
            headers = {'User-Agent': 'Mozilla/5.0'}
            if referer:
                headers['Referer'] = referer
            body = urlencode(data).encode() if data is not None else None
            if body:
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
            try:
                with session.request('POST' if body else 'GET', url, data=body, headers=headers,
                        timeout=(15, 30), stream=True, allow_redirects=False, verify=True) as response:
                    raw = bytearray()
                    for chunk in response.iter_content(65536):
                        raw.extend(chunk)
                        if len(raw) > 8 * 1024**2:
                            raise ValueError('Exchange response exceeds bounded archive size')
                    raw = bytes(raw)
                    status, final_url = response.status_code, response.url
                    response_headers = dict(location=response.headers.get('Location'),
                        content_type=response.headers.get('Content-Type'))
            except (requests.RequestException, ValueError) as error:
                failures.append(dict(label=label, request_url=url, request_data=data,
                    observed_at=clock().isoformat(), error_type=type(error).__name__, reason=str(error)))
                return None
            digest = sha256(raw).hexdigest()
            if shutil.disk_usage(directory).free - len(raw) < 2 * 1024**3:
                raise OSError('Preserve 2 GiB database disk reserve')
            path = directory / (digest + '.bin')
            if path.exists():
                if sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError('Retained exchange response hash mismatch')
            else:
                with path.open('xb') as stream:
                    stream.write(raw)
            document = dict(label=label, raw=raw, sha256=digest, local_path=str(path),
                request_url=url, url=final_url, request_data=data, fetched_at=clock().isoformat(),
                http_status=status, **response_headers)
            documents.append(document)
            return document

        fetch('SZSE_A', SZSE_URL, params={'SHOWTYPE': 'xlsx', 'CATALOGID': '1110', 'TABKEY': 'tab1'})
        for kind in ('1', '8'):
            fetch('SSE_' + kind, SSE_URL, params=dict(STOCK_TYPE=kind,
                sqlId='COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L', COMPANY_STATUS='2,4,5,7,8',
                type='inParams', isPagination='true', **{'pageHelp.pageSize': '10000',
                'pageHelp.pageNo': '1', 'pageHelp.beginPage': '1', 'pageHelp.endPage': '1'}),
                referer='https://www.sse.com.cn/assortment/stock/list/share/')
        index, pages = 0, 1
        while index < pages:
            document = fetch('BSE_' + str(index), BSE_URL, data={
                'page': str(index), 'typejb': 'T', 'xxfcbj[]': '2', 'xxzqdm': '',
                'sortfield': 'xxzqdm', 'sorttype': 'asc'})
            if document is None or document['http_status'] != 200:
                break
            try:
                page = parse_bse_page(document['raw'])
                pages = int(page['totalPages'])
                if not 1 <= pages <= 200 or int(page['number']) != index:
                    break
            except (ValueError, KeyError, TypeError, UnicodeError):
                break
            index += 1
    return replay_official_venue_coverage(documents, request_failures=failures,
        started_at=started, available_at=clock())
