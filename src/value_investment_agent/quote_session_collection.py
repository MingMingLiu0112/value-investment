"""Bounded dated-quote collection with shared immutable response documents."""
import base64
import hashlib
import re
from datetime import datetime, timedelta, timezone

import requests

from .quote_sessions import CHINA, CALENDAR_PATH, SSE_2026_CLOSURE_NOTICE_URL


def collect_session_bundle(symbols, *, session=None, clock=None, batch_size=50):
    symbols = list(symbols)
    if (not symbols or len(symbols) > 1000
            or any(not isinstance(s, str) or not re.fullmatch(r'\d{6}', s) for s in symbols)
            or len(set(symbols)) != len(symbols)
            or not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= 50):
        raise ValueError('Unique bounded symbols and batch size required')
    clock = clock or (lambda: datetime.now(timezone.utc))
    started = clock()
    if started.utcoffset() is None:
        raise ValueError('Timezone-aware collection clock required')
    owned = session is None
    session = session or requests.Session()
    if owned:
        session.trust_env = False
    documents, failures = {}, []

    def fetch(url, *, params=None, headers=None):
        try:
            response = session.get(url, params=params, headers=headers, timeout=(10, 20))
            raw = response.content
            if len(raw) > 1_000_000:
                raise ValueError('Bounded response exceeds maximum size')
            # Identity includes retrieval time: unchanged bytes must not refresh old evidence.
            stamp = clock().isoformat()
            digest = hashlib.sha256(raw).hexdigest()
            identity = hashlib.sha256((response.url + '\n' + stamp + '\n' + digest).encode()).hexdigest()
            documents[identity] = {'source_url': response.url, 'fetched_at': stamp,
                                   'sha256': digest, 'http_status': response.status_code,
                                   'raw_base64': base64.b64encode(raw).decode('ascii')}
            response.raise_for_status()
            return identity
        except (requests.RequestException, ValueError) as error:
            failures.append({'requested_url': url, 'params': params, 'error': str(error)})
            return None

    references = {}
    try:
        calendar_refs = []
        sse_calendar_refs = []
        if any(s.startswith(('0', '3')) for s in symbols):
            first = started.astimezone(CHINA).date().replace(day=1)
            for month in ((first - timedelta(days=1)).strftime('%Y-%m'), first.strftime('%Y-%m')):
                calendar_refs.append(fetch('https://www.szse.cn' + CALENDAR_PATH,
                    params={'month': month}, headers={'Referer': 'https://www.szse.cn/'}))
        if started.astimezone(CHINA).year == 2026 and any(s.startswith('6') for s in symbols):
            sse_calendar_refs.append(fetch(SSE_2026_CLOSURE_NOTICE_URL,
                                           headers={'Referer': 'https://www.sse.com.cn/disclosure/dealinstruc/closed/'}))
        for offset in range(0, len(symbols), batch_size):
            batch = symbols[offset:offset + batch_size]
            identities = [('sz' if s.startswith(('0', '3')) else 'sh' if s.startswith('6') else 'bj') + s
                          for s in batch]
            tx = fetch('https://qt.gtimg.cn/q=' + ','.join(identities))
            sina = fetch('https://hq.sinajs.cn/list=' + ','.join(identities),
                         headers={'Referer': 'https://finance.sina.com.cn/'})
            for symbol in batch:
                venue = 'SZSE' if symbol.startswith(('0', '3')) else 'SSE' if symbol.startswith('6') else 'BSE'
                references[symbol] = {'symbol': symbol, 'calendar_exchange': venue,
                    'document_refs': {'tencent': tx, 'sina': sina,
                                      'calendar_documents': (list(calendar_refs) if venue == 'SZSE'
                                                             else list(sse_calendar_refs) if venue == 'SSE' else [])}}
    finally:
        if owned:
            session.close()
    return {'version': 'quote-session-collection-v1', 'started_at': started.isoformat(),
            'finished_at': clock().isoformat(), 'documents': documents,
            'references': references, 'request_failures': failures,
            'status': 'partial_failure' if failures else 'collected_not_verified'}


def resolve_session_reference(reference, documents):
    """Resolve only explicitly linked documents; no latest-document fallback."""
    if not isinstance(reference, dict) or not isinstance(documents, dict):
        raise ValueError('Shared quote documents and explicit references required')
    refs = reference.get('document_refs')
    if not isinstance(refs, dict) or set(refs) != {'tencent', 'sina', 'calendar_documents'}:
        raise ValueError('Complete session document references required')
    if any(k in reference for k in ('tencent', 'sina', 'calendar_documents')):
        raise ValueError('Ambiguous inline and referenced quote evidence')

    def document(identity):
        if not isinstance(identity, str) or identity not in documents:
            raise ValueError('Referenced quote document missing')
        item = documents[identity]
        if not isinstance(item, dict) or item.get('http_status') != 200:
            raise ValueError('Referenced response was not successful')
        expected = hashlib.sha256((item['source_url'] + '\n' + item['fetched_at']
                                   + '\n' + item['sha256']).encode()).hexdigest()
        if identity != expected:
            raise ValueError('Shared document identity mismatch')
        return item

    calendars = refs['calendar_documents']
    if not isinstance(calendars, list) or len(calendars) > 3:
        raise ValueError('Invalid calendar references')
    return {'symbol': reference.get('symbol'), 'calendar_exchange': reference.get('calendar_exchange'),
            'tencent': document(refs['tencent']), 'sina': document(refs['sina']),
            'calendar_documents': [document(identity) for identity in calendars]}
